"""Offline tests. No real credentials, provider calls or production state."""
from contextlib import ExitStack
import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
import uvicorn

from alphagenie import config, validation
from alphagenie.security import child_environment, redact
from alphagenie.runner import JobManager
from app import job_store, manuscript_release as release, manuscript_view as view

TSV = "gene_symbol\tchrom\tpos1\tref\talt\nTEST\tchr1\t9000\tTCCG\tT\n"


class ValidationTests(unittest.TestCase):
    def test_lengths_and_simple_alleles(self):
        for length in validation.LENGTHS:
            self.assertEqual(validation.parse_variants(TSV, length)[0]["sequence_length"], length)
        for length in (16000, 16385, 1000000):
            with self.assertRaises(ValueError):
                validation.parse_variants(TSV, length)
        for pair in ("N\tT", "T\tT", "CCG\tTA", "CC\tCCT"):
            with self.assertRaises(ValueError):
                validation.parse_variants(TSV.replace("TCCG\tT", pair))

    def test_paths_duplicates_and_column_injection(self):
        with self.assertRaises(ValueError):
            validation.parse_variants(TSV.replace("alt\n", "alt\tvariant_group_id\n").replace("TCCG\tT\n", "TCCG\tT\t../escape\n"))
        with self.assertRaises(ValueError):
            validation.parse_variants(TSV + TSV.splitlines()[1] + "\n")
        with self.assertRaises(ValueError):
            validation.parse_variants(TSV.replace("gene_symbol\t", "api_key\t"))
        with self.assertRaises(ValueError):
            validation.parse_variants(TSV, null_depth=9)

    def test_reference_preflight_no_key_to_samtools(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fasta, gtf, sam = root / "hg38.fa", root / "gencode.gtf", root / "samtools"
            fasta.write_text(">chr1\nTCCG\n")
            Path(str(fasta)+".fai").write_text("chr1\t1000000\t0\t60\t61\n")
            gtf.write_text('chr1\ttest\tgene\t8000\t10000\t.\t+\t.\tgene_name "TEST";\n')
            sam.write_text("test fixture; never executed")
            sam.chmod(0o700)
            cfg = {"fasta": str(fasta), "gtf": str(gtf), "samtools": str(sam)}
            rows = validation.parse_variants(TSV, 16384)
            with patch.dict(os.environ, {"ALPHA_GENOME_API_KEY": "synthetic-private-key-canary"}), patch.object(
                validation.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, ">chr1\nTCCG\n", "")
            ) as run:
                self.assertEqual(validation.preflight(rows, cfg)["api_calls"], 0)
                self.assertNotIn("ALPHA_GENOME_API_KEY", run.call_args.kwargs["env"])
                run.return_value.stdout = ">chr1\nAAAA\n"
                with self.assertRaisesRegex(ValueError, "REF does not match"):
                    validation.preflight(rows, cfg)
            gtf.write_text('chr2\ttest\tgene\t8000\t10000\t.\t+\t.\tgene_name "TEST";\n')
            with self.assertRaisesRegex(ValueError, "target gene"):
                validation.preflight(rows, cfg)


class PrivateStateTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.dict(os.environ, {"ALPHAGENIE_HOME": str(self.root / "state"),
                                                        "ALPHA_GENOME_API_KEY": ""}))

    def test_credential_permissions_and_value_not_returned(self):
        state = config.state_dir()
        path = state / "credentials.json"
        config.private_write(path, json.dumps({"api_key": "synthetic-credential-not-a-real-key"}))
        self.assertEqual(state.stat().st_mode & 0o777, 0o700)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertTrue(config.key_available())
        self.assertEqual(config.read_key(), "synthetic-credential-not-a-real-key")
        path.chmod(0o644)
        with self.assertRaises(ValueError):
            config.read_key()

    def test_refuse_in_repo_state_and_symlink(self):
        with patch.dict(os.environ, {"ALPHAGENIE_HOME": str(config.ROOT / "runtime")}):
            with self.assertRaises(ValueError):
                config.state_dir()
        link = self.root / "link"
        link.symlink_to(self.root)
        with patch.dict(os.environ, {"ALPHAGENIE_HOME": str(link)}):
            with self.assertRaises(ValueError):
                config.state_dir()

    def test_secret_redaction_in_logs_json_db_and_child_env(self):
        from worker import run_single_variant_job as worker
        key = "synthetic-private-key-canary"
        state = config.state_dir()
        with patch.dict(os.environ, {"ALPHA_GENOME_API_KEY": key, "AWS_SECRET_ACCESS_KEY": "not-real",
                                     "HTTPS_PROXY": "https://not-used.invalid", "AG_WEB_ENABLE_API_FULL": "1"}):
            clean = child_environment()
            for name in ("ALPHA_GENOME_API_KEY", "AWS_SECRET_ACCESS_KEY", "HTTPS_PROXY", "AG_WEB_ENABLE_API_FULL"):
                self.assertNotIn(name, clean)
            self.assertNotIn(key, redact("Provider error: " + key))
            worker.write_text(state / "error.txt", key)
            worker.write_json(state / "status.json", {"reason": key, "api_key": "another-value"})
            manager = JobManager()
            job_store.create_job(manager.db, job_id="a"*32, run_mode="api_full", input_payload={}, job_dir=state / "jobs" / ("a"*32))
            job_store.update_job(manager.db, "a"*32, message=key, result={"reason": key})
            for name in ("error.txt", "status.json", "jobs.sqlite"):
                self.assertNotIn(key.encode(), (state / name).read_bytes())
            worker.run_command([sys.executable, "-c", "import os; print(os.environ['ALPHA_GENOME_API_KEY'])"],
                               cwd=state, log_path=state / "child.log", env=child_environment(api_key=key))
            self.assertNotIn(key, (state / "child.log").read_text())

    def test_running_lock_prevents_recovery_and_duplicate_job(self):
        manager = JobManager()
        job_store.create_job(manager.db, job_id="b"*32, run_mode="api_full", input_payload={}, job_dir=manager.jobs / ("b"*32))
        held = manager.acquire_job_lock()
        try:
            other = JobManager()
            other.recover()
            self.assertEqual(job_store.get_job(manager.db, "b"*32)["status"], "submitted")
            with self.assertRaisesRegex(ValueError, "still alive"):
                other.acquire_job_lock()
        finally:
            held.close()
        manager.recover()
        self.assertEqual(job_store.get_job(manager.db, "b"*32)["status"], "interrupted")

    def test_inherited_lock_survives_parent_descriptor_close(self):
        manager = JobManager()
        held = manager.acquire_job_lock()
        # Harmless child retains the descriptor until stdin closes; no inference.
        child = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"],
                                 pass_fds=(held.fileno(),), stdin=subprocess.PIPE)
        held.close()
        try:
            with self.assertRaises(ValueError):
                manager.acquire_job_lock()
        finally:
            child.communicate(timeout=5)
        manager.acquire_job_lock().close()

    def test_legacy_mode_rejected_before_data_or_api(self):
        from worker import run_single_variant_job as worker
        with patch.object(worker, "update_job") as update, patch.object(worker, "write_text"), patch.object(
            worker, "load_demo_outputs", side_effect=AssertionError("legacy")
        ), patch.object(worker, "run_api_full", side_effect=AssertionError("API")), patch.object(worker, "make_variant_tsv") as write:
            worker.run_job(db_path=str(self.root / "no-db"), job_id="x", payload={}, run_mode="demo_cached",
                           job_dir=str(self.root / "no-output"), v04_reference_run="missing", v04_pipeline_dir="missing",
                           hg38_fasta="missing", gencode_gtf="missing")
            write.assert_not_called()
            self.assertEqual(update.call_args.kwargs["status"], "failed")

    def test_launch_storage_failure_releases_lock(self):
        from alphagenie import runner
        manager = JobManager()
        with patch.object(runner, "read_config", return_value={}), patch.object(runner, "preflight", return_value={}), patch.object(
            runner, "read_key", return_value="synthetic-only"
        ), patch.object(job_store, "create_job", side_effect=OSError("fixture storage failure")):
            with self.assertRaises(OSError):
                manager.launch(validation.parse_variants(TSV))
        manager.acquire_job_lock().close()

    def test_shutdown_tolerates_process_exit_race(self):
        from alphagenie import runner
        manager = JobManager()
        manager.process = Mock(pid=999999, poll=Mock(return_value=None), wait=Mock(return_value=0))
        manager.current_id = "a"*32
        with patch.object(runner.os, "killpg", side_effect=ProcessLookupError) as kill, patch.object(job_store, "update_job"):
            manager.stop()
        self.assertEqual(kill.call_count, 2)
        self.assertTrue(manager.closed)


class HttpTests(unittest.TestCase):
    def test_old_jobs_are_not_relabelled_as_brain9(self):
        from worker.brain9 import VERSION
        from worker.rna_curve import SPEC_ID
        state = config.state_dir()
        db = state / "jobs.sqlite"
        for letter, payload in (("c", {"analysis_mode": "custom_api_local_brain6"}),
                                ("d", {"classification_version": VERSION}),
                                ("e", {"classification_version": VERSION, "curve_spec_id": SPEC_ID})):
            job_store.create_job(db, job_id=letter*32, run_mode="api_full", input_payload=payload,
                                 job_dir=state / "jobs" / (letter*32))
            response = self.request("GET", "/api/local/jobs/" + letter*32)
            self.assertEqual(response[0], 200)
            self.assertIn("Legacy Brain6" if letter == "c" else "Brain9 (adult 8 + Embryo)", response[2]["endpoint"])
            self.assertIn("Frontal cortex" if letter == "e" else "Legacy curve", response[2]["rna_curve"])

    @classmethod
    def setUpClass(cls):
        cls.stack = ExitStack()
        cls.root = Path(cls.stack.enter_context(tempfile.TemporaryDirectory()))
        cls.stack.enter_context(patch.dict(os.environ, {"ALPHAGENIE_HOME": str(cls.root / "state"), "ALPHA_GENOME_API_KEY": ""}))
        from alphagenome.models import dna_client
        cls.stack.enter_context(patch.object(dna_client, "create", side_effect=AssertionError("API forbidden in offline tests")))
        from alphagenie.server import create_app
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        cls.port = sock.getsockname()[1]
        cls.app = create_app(cls.port)
        cls.server = uvicorn.Server(uvicorn.Config(cls.app, host="127.0.0.1", port=cls.port, log_level="error", access_log=False))
        cls.thread = threading.Thread(target=cls.server.run, kwargs={"sockets": [sock]}, daemon=True)
        cls.thread.start()
        deadline = time.monotonic()+10
        while not cls.server.started and cls.thread.is_alive() and time.monotonic() < deadline:
            time.sleep(.01)
        if not cls.server.started:
            raise RuntimeError("Test server failed to start")
        cls.token = cls.request("GET", "/api/local/status")[2]["token"]

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(timeout=12)
        cls.stack.close()

    @classmethod
    def request(cls, method, path, body=None, headers=None, raw=False):
        conn = http.client.HTTPConnection("127.0.0.1", cls.port, timeout=30)
        try:
            conn.request(method, path, body=None if body is None else json.dumps(body), headers=headers or {})
            response = conn.getresponse()
            content = response.read()
            if raw:
                return response.status, dict(response.getheaders()), content
            try:
                data = json.loads(content)
            except (ValueError, UnicodeDecodeError):
                data = content
            return response.status, dict(response.getheaders()), data
        finally:
            conn.close()

    def auth(self):
        return {"Origin": f"http://127.0.0.1:{self.port}", "X-AlphaGENIE-Token": self.token, "Content-Type": "application/json"}

    def test_page_status_privacy_and_no_operator_endpoints(self):
        code, headers, html = self.request("GET", "/")
        self.assertEqual(code, 200)
        self.assertIn(b"AlphaGENome-Integrated Explorer", html)
        self.assertIn(b"My analyses", html)
        self.assertNotIn("cloudflare", headers["content-security-policy"])
        s = self.request("GET", "/api/local/status")[2]
        self.assertFalse(s["key_configured"])
        self.assertNotIn("api_key", s)
        for path in ("/api/feedback", "/api/feedback/config", "/api/jobs", "/classic", "/.env", "/api/local/key"):
            self.assertEqual(self.request("GET", path)[0], 404)

    def test_host_origin_token_and_consent_fail_closed(self):
        self.assertEqual(self.request("GET", "/", headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.request("GET", "/api/local/status", headers={"Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.request("POST", "/api/local/jobs", {"tsv": TSV})[0], 403)
        self.assertEqual(self.request("POST", "/api/local/jobs", {"tsv": TSV}, self.auth())[0], 422)
        headers = self.auth() | {"Origin": "null"}
        self.assertEqual(self.request("POST", "/api/local/jobs", {"tsv": TSV, "consent": True}, headers)[0], 403)
        self.assertEqual(job_store.list_jobs(self.app.state.manager.db), [])

    def test_submission_shape_requires_supported_length_and_no_key_field(self):
        for body in ({"tsv": TSV, "sequence_length": 12345, "consent": True},
                     {"tsv": TSV, "consent": True, "api_key": "must-not-be-accepted"}):
            with patch.object(self.app.state.manager, "launch", side_effect=AssertionError("not eligible")):
                self.assertEqual(self.request("POST", "/api/local/jobs", body, self.auth())[0], 422)
        with patch.object(self.app.state.manager, "launch", return_value="c"*32) as launch:
            response = self.request("POST", "/api/local/jobs", {"tsv": TSV, "consent": True}, self.auth())
            self.assertEqual(response[0], 202)
            self.assertEqual(response[2]["endpoint"], "Brain9")
            self.assertEqual(launch.call_args.args[0][0]["null_depth"], 1000)

    def test_saved_data_all_55_downloads_preserved_without_api(self):
        count = 0
        for key in ("rbfox1", "ptchd1", "ccg17"):
            code, _, value = self.request("GET", "/api/explorer/"+key)
            self.assertEqual(code, 200)
            self.assertEqual(value["result"], release.payload(key))
            for url in value["result"]["downloads"].values():
                code, _, content = self.request("GET", url, raw=True)
                self.assertEqual(code, 200)
                self.assertEqual(hashlib.sha256(content).hexdigest(), release.manifest()["files"][key+"/"+url.rsplit("/", 1)[1]])
                count += 1
        self.assertEqual(count, 55)

    def test_stacked_pdf_dimensions_and_path_restriction(self):
        code, _, pdf = self.request("GET", "/api/explorer/rbfox1/export/pdf?figure_width_mm=174&font_size_pt=6.5&top_panel_height_mm=64&effect_panel_height_mm=68")
        self.assertEqual(code, 200)
        self.assertTrue(pdf.startswith(b"%PDF"))
        box = re.search(rb'/MediaBox\s*\[\s*0\s+0\s+([0-9.]+)\s+([0-9.]+)', pdf)
        self.assertAlmostEqual(float(box[1])*25.4/72, 174, places=5)
        self.assertAlmostEqual(float(box[2])*25.4/72, 136, places=5)
        self.assertEqual(self.request("GET", "/api/explorer/rbfox1/export/pdf?font_size_pt=2")[0], 422)
        self.assertEqual(self.request("GET", "/api/local/jobs/../../credentials.json")[0], 404)


class FrozenStatisticsTests(unittest.TestCase):
    def test_raw_thousand_nulls_reproduce_saved_effects_and_p(self):
        for key in ("rbfox1", "ptchd1"):
            data = release.payload(key)
            with np.load(release.asset(f"{key}/scores.npz"), allow_pickle=False) as scores:
                self.assertEqual(scores["null_raw"].shape, (1000, 371))
                np.testing.assert_allclose(scores["track_null_median"], np.median(scores["null_raw"], axis=0))
                np.testing.assert_allclose(scores["real_effect"], scores["real_raw"] - scores["track_null_median"])
                tracks = list(scores["track_keys"])
                indices = [[tracks.index(t) for t in group["track_keys"]] for group in data["groups"] if group["included_in_brain9"]]
                real = float(np.median([np.median(scores["real_effect"][i]) for i in indices]))
                nulls = np.median(np.stack([np.median(scores["null_effect"][:, i], axis=1) for i in indices]), axis=0)
                self.assertAlmostEqual(real, data["analysis"]["real_consensus_delta"], places=11)
                center = np.median(nulls)
                p = (1 + np.sum(np.abs(nulls-center) >= abs(real-center)))/1001
                self.assertAlmostEqual(p, data["analysis"]["empirical_p_two_sided"], places=14)


class CohortAndTrackGuards(unittest.TestCase):
    def test_cortex_does_not_fallback_to_whole_brain(self):
        from worker.rna_curve import choose_frontal_cortex_track, TRACK_SPEC
        with self.assertRaises(ValueError):
            choose_frontal_cortex_track(pd.DataFrame([{"ontology_curie": "UBERON:0000955", "biosample_name": "brain"}]))
        data = pd.DataFrame([{"ontology_curie": "UBERON:0000955"}, TRACK_SPEC])
        self.assertEqual(choose_frontal_cortex_track(data), 1)

    def test_partial_cohort_is_withheld(self):
        from worker import run_multi_variant_job as multi
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(multi, "create_job"), patch.object(multi, "update_job") as update, patch.object(
                multi, "run_job"
            ), patch.object(multi, "get_job", side_effect=[{"status": "failed"}, {"status": "complete"}]), patch.object(
                multi, "load_single_result", return_value={"fixture": True}
            ), patch.object(multi, "combine_single_results", side_effect=AssertionError("Reduced family forbidden")) as combine:
                multi.run_multi_variant_job(db_path=str(root / "unused"), job_id="f"*32,
                    payload={"rows": [{"variant_group_id": "a"}, {"variant_group_id": "b"}], "analysis_mode": "custom_api_local_brain9"},
                    job_dir=str(root), v04_reference_run="unused", v04_pipeline_dir="unused", hg38_fasta="unused", gencode_gtf="unused")
                combine.assert_not_called()
                self.assertEqual(update.call_args.kwargs["status"], "failed")
                self.assertIn("1/2", update.call_args.kwargs["message"])

    def test_missing_cosine_reference_is_not_replaced(self):
        from worker import run_multi_variant_job as multi
        from worker.brain9 import provenance, SCOPE
        item = {"summary": {"classification": provenance(), "primary_effect_scope": SCOPE, "variant_group_id": "present", "gene_symbol": "TEST", "empirical_p_two_sided": .1,
                            "empirical_p_observed_direction": .2},
                "group": pd.DataFrame({"display_group": multi.BRAIN_GROUPS, "median_effect": [.1]*9}),
                "source": pd.DataFrame({"effect": [.1], "track_key": ["fixture"], "display_group": [multi.BRAIN_GROUPS[0]]}), "job": {"job_id": "present"}}
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "reference is unavailable"):
                multi.combine_single_results(job_id="test", payload={"rows": [{"variant_group_id": "present"}], "reference_variant_group_id": "missing"},
                                             single_results=[item], results_dir=Path(temp))

    def test_multi_html_escapes_user_labels(self):
        from worker.run_multi_variant_job import write_multi_plot_html
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            svg = root / "plot.svg"
            svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
            write_multi_plot_html(root / "plot.html", svg, {"dataset_name": "<script>x</script>", "reference_variant_group_id": "<img>"})
            text = (root / "plot.html").read_text()
            self.assertNotIn("<script>", text)
            self.assertNotIn("<img>", text)


if __name__ == "__main__":
    unittest.main()
