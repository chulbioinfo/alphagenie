"""No-login local boundaries and resource limits; temporary dummy state only."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import http.client
import io
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import uvicorn

from app import job_store

TSV = "gene_symbol\tchrom\tpos1\tref\talt\nTEST\tchr1\t9000\tTCCG\tT\n"


class LocalLimitTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.dict(os.environ, {"ALPHAGENIE_HOME": str(self.root / "state"), "ALPHA_GENOME_API_KEY": ""}))
        from alphagenie import server
        from alphagenome.models import dna_client
        self.stack.enter_context(patch.object(dna_client, "create", side_effect=AssertionError("No provider calls")))
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        self.port = sock.getsockname()[1]
        self.origin = f"http://127.0.0.1:{self.port}"
        self.app = server.create_app(self.port)
        self.now = 1000.0
        self.app.state.analysis_budget.clock = self.app.state.render_budget.clock = lambda: self.now
        self.server = uvicorn.Server(uvicorn.Config(self.app, host="127.0.0.1", port=self.port, log_level="error",
                                                    access_log=False, proxy_headers=False))
        self.thread = threading.Thread(target=self.server.run, kwargs={"sockets": [sock]}, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        deadline = time.monotonic() + 10
        while not self.server.started and self.thread.is_alive() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue(self.server.started)
        self.token = self.request("GET", "/api/local/status")[2]["token"]

    def stop_server(self):
        self.server.should_exit = True
        self.thread.join(timeout=12)
        self.assertFalse(self.thread.is_alive())

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            conn.request(method, path, body=None if body is None else json.dumps(body), headers=headers or {})
            response = conn.getresponse()
            content = response.read()
            try:
                content = json.loads(content)
            except (ValueError, UnicodeDecodeError):
                pass
            return response.status, dict(response.getheaders()), content
        finally:
            conn.close()

    def write_headers(self):
        return {"Origin": self.origin, "Content-Type": "application/json", "X-AlphaGENIE-Token": self.token}

    def test_no_login_status_local_reads_and_downloads_without_cookies(self):
        manager = self.app.state.manager
        jid = "f" * 32
        directory = manager.jobs / jid
        directory.mkdir(mode=0o700)
        artifact = directory / "dummy.tsv"
        artifact.write_text("synthetic\tprivate\n")
        job_store.create_job(manager.db, job_id=jid, run_mode="api_full", input_payload={}, job_dir=directory)
        job_store.update_job(manager.db, jid, status="complete", result={"test_tsv": str(artifact)})
        code, headers, status = self.request("GET", "/api/local/status")
        self.assertEqual(code, 200)
        self.assertRegex(status["token"], r"^[A-Za-z0-9_-]{43}$")
        self.assertNotIn("api_key", status)
        self.assertNotIn("csrf_token", status)
        self.assertNotIn("set-cookie", headers)
        self.assertEqual(status["ui_version"], "0.23")
        self.assertEqual(self.request("GET", "/api/local/jobs")[2]["jobs"][0]["job_id"], jid)
        self.assertEqual(self.request("GET", f"/api/local/jobs/{jid}/files/test_tsv")[2], b"synthetic\tprivate\n")
        for path in ("/api/local/session", "/api/local/logout"):
            self.assertEqual(self.request("GET", path)[0], 404)
            self.assertEqual(self.request("POST", path, {}, self.write_headers())[0], 404)

    def test_exact_host_origin_token_and_json_boundary(self):
        for overrides in ({"Host": "localhost:" + str(self.port)}, {"Host": "evil.invalid"}, {"Origin": "null"},
                          {"Origin": "http://127.0.0.1:1"}, {"Origin": ""}, {"Sec-Fetch-Site": "cross-site"},
                          {"X-AlphaGENIE-Token": "forged"}, {"X-AlphaGENIE-Token": "é"}):
            code, headers, _ = self.request("POST", "/api/local/validate", {"tsv": TSV}, self.write_headers() | overrides)
            self.assertEqual(code, 403)
            self.assertEqual(headers["cache-control"], "no-store")
        self.assertEqual(self.request("POST", "/api/local/validate", {"tsv": TSV})[0], 403)
        self.assertEqual(self.request("POST", "/api/local/validate", {"tsv": TSV},
                                      self.write_headers() | {"Content-Type": "text/plain"})[0], 415)
        from alphagenie.server import create_app
        restarted = create_app(self.port)
        self.assertFalse(hasattr(restarted.state, "sessions"))

    def test_no_login_preflight_and_explicit_mock_submission(self):
        from alphagenie import server
        with patch.object(server, "preflight", return_value={"api_calls": 0}) as preflight:
            result = self.request("POST", "/api/local/validate", {"tsv": TSV}, self.write_headers())
            self.assertEqual(result[0], 200)
            self.assertEqual(result[2]["api_calls"], 0)
            preflight.assert_called_once()
        with patch.object(self.app.state.manager, "launch", return_value="a" * 32) as launch:
            result = self.request("POST", "/api/local/jobs", {"tsv": TSV, "consent": True}, self.write_headers())
            self.assertEqual(result[0], 202)
            self.assertEqual(launch.call_args.args[0][0]["null_depth"], 1000)

    def test_analysis_admission_is_nonblocking_with_eight_per_minute_process_budget(self):
        from alphagenie import server
        entered, release = threading.Event(), threading.Event()

        def slow_preflight(*_):
            entered.set()
            if not release.wait(timeout=5):
                raise AssertionError("Test did not release preflight")
            return {"api_calls": 0}

        with patch.object(server, "preflight", side_effect=slow_preflight) as preflight, ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(self.request, "POST", "/api/local/validate", {"tsv": TSV}, self.write_headers())
            try:
                self.assertTrue(entered.wait(timeout=3))
                before = time.monotonic()
                code, headers, _ = self.request("POST", "/api/local/jobs", {"tsv": TSV, "consent": True}, self.write_headers())
                self.assertEqual(code, 503)
                self.assertEqual(headers["retry-after"], "1")
                self.assertLess(time.monotonic() - before, 1)
            finally:
                release.set()
            self.assertEqual(pending.result(timeout=5)[0], 200)
            preflight.assert_called_once()
        with patch.object(server, "preflight", return_value={"api_calls": 0}) as preflight:
            for _ in range(7):
                self.assertEqual(self.request("POST", "/api/local/validate", {"tsv": TSV}, self.write_headers())[0], 200)
            self.assertEqual(self.request("POST", "/api/local/validate", {"tsv": TSV}, self.write_headers())[0], 429)
            self.assertEqual(preflight.call_count, 7)
            self.now += 60
            self.assertEqual(self.request("POST", "/api/local/validate", {"tsv": TSV}, self.write_headers())[0], 200)

    def test_body_size_and_slow_upload_timeout_release_admission(self):
        from alphagenie import server
        self.assertEqual(self.request("POST", "/api/local/validate", {"tsv": "x" * 111000}, self.write_headers())[0], 413)
        with patch.object(server, "BODY_TIMEOUT_SECONDS", .05):
            conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
            try:
                conn.putrequest("POST", "/api/local/validate")
                for key, value in self.write_headers().items():
                    conn.putheader(key, value)
                conn.putheader("Content-Length", "100")
                conn.endheaders(b"{")
                response = conn.getresponse()
                self.assertEqual(response.status, 408)
                self.assertEqual(json.loads(response.read()), {"detail": "Request body timed out"})
            finally:
                conn.close()
        with patch.object(server, "preflight", return_value={"api_calls": 0}):
            self.assertEqual(self.request("POST", "/api/local/validate", {"tsv": TSV}, self.write_headers())[0], 200)

    def test_anonymous_render_admission_rejects_before_threadpool_and_recovers(self):
        from app import manuscript_view as view
        entered, release = threading.Event(), threading.Event()

        def slow_render(*_, **__):
            entered.set()
            if not release.wait(timeout=5):
                raise AssertionError("Test did not release render")
            return b"%PDF synthetic dummy figure"

        with patch.object(view, "render", side_effect=slow_render) as render, ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(self.request, "GET", "/api/explorer/rbfox1/export/pdf")
            try:
                self.assertTrue(entered.wait(timeout=3))
                before = time.monotonic()
                for path in ("/api/explorer/rbfox1/export/pdf", "/api/explorer/ptchd1/view-options", "/api/explorer/rbfox1/curve.svg"):
                    code, headers, _ = self.request("GET", path)
                    self.assertEqual(code, 503)
                    self.assertEqual(headers["retry-after"], "2")
                self.assertLess(time.monotonic() - before, 1)
                self.assertEqual(self.request("GET", "/api/explorer/tracks")[0], 200)
                render.assert_called_once()
            finally:
                release.set()
            self.assertEqual(pending.result(timeout=5)[0], 200)
        with patch.object(view, "render", return_value=b"%PDF synthetic dummy figure"):
            self.assertEqual(self.request("GET", "/api/explorer/rbfox1/export/pdf")[0], 200)

    def test_render_budget_ignores_forged_forwarded_identity(self):
        from app import manuscript_view as view
        with patch.object(view, "render", return_value=b"%PDF synthetic dummy figure") as render:
            for index in range(30):
                self.assertEqual(self.request("GET", "/api/explorer/rbfox1/export/pdf",
                                              headers={"X-Forwarded-For": f"192.0.2.{index}"})[0], 200)
            code, headers, _ = self.request("GET", "/api/explorer/rbfox1/export/pdf")
            self.assertEqual(code, 429)
            self.assertEqual(headers["retry-after"], "60")
            self.assertEqual(render.call_count, 30)
            self.now += 60
            self.assertEqual(self.request("GET", "/api/explorer/rbfox1/export/pdf")[0], 200)


class NoLoginCliTests(unittest.TestCase):
    def test_noninteractive_serve_has_ordinary_url_without_credential_reads(self):
        from alphagenie import __main__ as cli, config, server
        stdout = io.StringIO()
        fake_app = object()
        with patch.object(sys, "argv", ["alphagenie", "serve", "--port", "8877"]), patch.object(sys, "stdout", stdout), patch.object(
            config, "read_key", side_effect=AssertionError("No credential reads")
        ), patch.object(server, "create_app", return_value=fake_app) as create, patch("uvicorn.run") as run:
            cli.main()
        create.assert_called_once_with(8877)
        self.assertIn("http://127.0.0.1:8877/", stdout.getvalue())
        self.assertIn("No login", stdout.getvalue())
        self.assertNotIn("bootstrap", stdout.getvalue())
        self.assertIs(run.call_args.args[0], fake_app)
        self.assertFalse(run.call_args.kwargs["access_log"])


if __name__ == "__main__":
    unittest.main()
