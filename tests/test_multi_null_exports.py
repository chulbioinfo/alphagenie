"""Offline cohort export/registration checks with synthetic child results only."""
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from worker import brain9
from worker import run_multi_variant_job as multi


class MultiNullExportTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        # The synthetic fixtures need no redaction/credential lookup.
        self.stack.enter_context(patch("worker.run_single_variant_job.redact", side_effect=lambda value: value))
        self.stack.enter_context(patch.object(multi, "make_multi_plot"))
        self.stack.enter_context(patch.object(multi, "write_multi_plot_html"))
        self.job_id = "a" * 32
        self.rows = [{"variant_group_id": name, "gene_symbol": "TEST"} for name in ("first", "second")]
        self.payload = {
            "rows": self.rows,
            "analysis_mode": brain9.ANALYSIS_MODE,
            "reference_variant_group_id": "first",
        }

    def child_result(self, index, *, include_nulls=True):
        row = self.rows[index]
        child_root = self.root / "single_variant_jobs" / f"{index + 1:02d}_{row['variant_group_id']}"
        results = child_root / "results"
        results.mkdir(parents=True)
        if include_nulls:
            pd.DataFrame({"null_id": ["001", "0002", "NA"], "consensus_effect": [-.1, 0., .1]}).to_csv(
                results / "null_consensus.tsv", sep="\t", index=False)
        groups = [group for group, _ in brain9.FULL_GROUP_ORDER]
        return {
            "job": {"job_id": f"{self.job_id}_{index + 1:02d}", "job_dir": str(child_root),
                    "status": "complete", "run_mode": "api_full"},
            "summary": {**row, "classification": brain9.provenance(), "primary_effect_scope": brain9.SCOPE,
                        "empirical_p_two_sided": .5, "empirical_p_observed_direction": .25,
                        "real_consensus_delta": .1, "n_null_consensus": 3},
            "group": pd.DataFrame({"display_group": groups, "median_effect": [.1] * len(groups)}),
            "source": pd.DataFrame({"variant_group_id": [row["variant_group_id"]] * len(groups),
                                    "track_key": [f"track_{i}" for i in range(len(groups))],
                                    "display_group": groups, "effect": [.1] * len(groups)}),
        }

    def run_cohort(self, items):
        with patch.object(multi, "create_job"), patch.object(multi, "update_job") as update, patch.object(
            multi, "run_job"
        ) as run_child, patch.object(multi, "get_job", side_effect=[item["job"] for item in items]), patch.object(
            multi, "load_single_result", side_effect=[item for item in items if item["job"]["status"] == "complete"]
        ):
            multi.run_multi_variant_job(
                db_path=str(self.root / "unused.sqlite"), job_id=self.job_id, payload=self.payload,
                job_dir=str(self.root), v04_reference_run="unused", v04_pipeline_dir="unused",
                hg38_fasta="unused", gencode_gtf="unused")
        self.assertEqual(run_child.call_count, 2)
        return update.call_args.kwargs

    def test_complete_null_table_is_registered_and_preserves_identifier_strings(self):
        items = [self.child_result(i) for i in range(2)]
        final = self.run_cohort(items)
        self.assertEqual(final["status"], "complete")
        exported = Path(final["result"]["multi_null_consensus"])
        self.assertTrue(exported.is_file())
        self.assertEqual(exported, self.root / "results" / "multi_null_consensus.tsv")
        table = pd.read_csv(exported, sep="\t", dtype={"null_id": str}, keep_default_na=False)
        self.assertEqual(table.columns.tolist(), ["variant_group_id", "null_id", "consensus_effect"])
        self.assertEqual(table.null_id.tolist(), ["001", "0002", "NA"] * 2)
        self.assertEqual(table.variant_group_id.tolist(), ["first"] * 3 + ["second"] * 3)
        summary = json.loads((self.root / "results" / "multi_consensus_summary.json").read_text())
        self.assertEqual(summary["source_tables"]["null_consensus"], exported.name)

    def test_missing_child_null_table_does_not_register_a_partial_or_stale_export(self):
        items = [self.child_result(0), self.child_result(1, include_nulls=False)]
        results = self.root / "results"
        results.mkdir()
        stale = results / "multi_null_consensus.tsv"
        stale.write_text("prior export; not current cohort\n")
        final = self.run_cohort(items)
        self.assertEqual(final["status"], "complete")
        self.assertNotIn("multi_null_consensus", final["result"])
        summary = json.loads((results / "multi_consensus_summary.json").read_text())
        self.assertNotIn("null_consensus", summary["source_tables"])
        self.assertEqual(stale.read_text(), "prior export; not current cohort\n")

    def test_failed_child_still_withholds_all_cohort_outputs(self):
        items = [self.child_result(i) for i in range(2)]
        items[1]["job"]["status"] = "failed"
        with patch.object(multi, "combine_single_results", side_effect=AssertionError("No partial cohorts")) as combine:
            final = self.run_cohort(items)
        combine.assert_not_called()
        self.assertEqual(final["status"], "failed")
        self.assertNotIn("result", final)
        self.assertFalse((self.root / "results" / "multi_null_consensus.tsv").exists())


if __name__ == "__main__":
    unittest.main()
