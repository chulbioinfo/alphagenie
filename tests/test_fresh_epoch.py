"""Offline fresh-run identity checks; the scoring subprocess is never executed."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from worker import run_single_variant_job as worker


class ScoringIntercepted(RuntimeError):
    """Signal that an authorized identity reached the mocked scorer boundary."""


class FreshEpochTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.environment = {
            "AG_WEB_ENABLE_API_FULL": "1",
            "ALPHA_GENOME_API_KEY": "synthetic-offline-only",
        }
        self.payload = {
            "ref": "TCCG", "alt": "T", "sequence_length": 16384,
            "null_depth": 1000,
        }

    def run_worker(self, payload):
        return worker.run_api_full(
            db_path=self.root / "unused.sqlite", job_id="offline-test",
            payload=payload, job_dir=self.root / "job",
            v04_pipeline_dir=self.root / "pipeline",
            hg38_fasta=self.root / "unused.fa",
            gencode_gtf=self.root / "unused.gtf", log_dir=self.root / "logs",
        )

    def test_missing_and_placeholder_epochs_stop_before_scoring_or_progress(self):
        for epoch in (None, "", "local_run_epoch_required", "post-indel-fix-2026-07-14"):
            for source in ("payload", "environment"):
                with self.subTest(epoch=epoch, source=source):
                    payload, environment = dict(self.payload), dict(self.environment)
                    if epoch is not None:
                        if source == "payload":
                            payload["inference_run_epoch"] = epoch
                        else:
                            environment["AG_INFERENCE_RUN_EPOCH"] = epoch
                    with patch.dict(os.environ, environment, clear=True), patch.object(
                        worker, "run_command", side_effect=AssertionError("Scoring must not start")
                    ) as score, patch.object(worker, "update_job") as progress:
                        with self.assertRaisesRegex(ValueError, "new explicit inference run epoch"):
                            self.run_worker(payload)
                    score.assert_not_called()
                    progress.assert_not_called()
                    self.assertEqual(list(self.root.iterdir()), [])

    def test_fresh_payload_or_local_job_epoch_reaches_scorer_unchanged(self):
        epoch = "0123456789abcdef0123456789abcdef"
        for source in ("payload", "environment"):
            with self.subTest(source=source):
                payload, environment = dict(self.payload), dict(self.environment)
                if source == "payload":
                    payload["inference_run_epoch"] = epoch
                else:
                    environment["AG_INFERENCE_RUN_EPOCH"] = epoch
                with patch.dict(os.environ, environment, clear=True), patch.object(
                    worker, "run_command", side_effect=ScoringIntercepted
                ) as score, patch.object(worker, "update_job"):
                    with self.assertRaises(ScoringIntercepted):
                        self.run_worker(payload)
                score.assert_called_once()
                self.assertTrue(score.call_args.args[0][1].endswith("00_score_real_variants_rna.py"))
                child_env = score.call_args.kwargs["env"]
                self.assertEqual(child_env["AG_INFERENCE_RUN_EPOCH"], epoch)
                self.assertEqual(child_env["AG_INFERENCE_BACKEND_REVISION"], "unresolved_server_default")
                self.assertEqual(child_env["AG_REQUESTED_MODEL_VERSION"], "server_default")


if __name__ == "__main__":
    unittest.main()
