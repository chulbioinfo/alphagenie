from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from worker import run_single_variant_job as worker
from brain9_fixtures import small_catalog, score_row


class PrimaryBrainCoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.real = pd.DataFrame({
            "display_group": worker.BRAIN_TISSUE_GROUPS,
            "median_effect": [1.0] * 9,
        })

    def nulls(self, count=2):
        return pd.DataFrame([
            {"null_id": str(i), "display_group": group, "effect": float(i)}
            for i in range(count) for group in worker.BRAIN_TISSUE_GROUPS
        ])

    def compute(self, null, real=None, requested=None):
        return worker.complete_primary_brain_consensus(
            self.real if real is None else real, null,
            all_null_ids=sorted(null["null_id"].unique()), requested_null_depth=requested,
            coverage_out=self.root / "coverage.json",
        )

    def test_missing_real_group_fails_with_coverage_receipt(self):
        with self.assertRaisesRegex(ValueError, "missing finite values"):
            self.compute(self.nulls(), self.real.iloc[:-1])
        receipt = json.loads((self.root / "coverage.json").read_text())
        self.assertEqual(receipt["missing_real_groups"], [worker.BRAIN_TISSUE_GROUPS[-1]])
        self.assertEqual(receipt["status"], "failed")

    def test_incomplete_null_excluded_in_exploratory_analysis(self):
        null = self.nulls(3).iloc[:-1]
        real, consensus, receipt = self.compute(null, requested=3)
        np.testing.assert_equal(real, [1] * 9)
        self.assertEqual(consensus.to_dict(), {"0": 0, "1": 1})
        self.assertEqual(receipt["excluded_incomplete_null_ids"], ["2"])
        self.assertEqual(receipt["status"], "warning")

    def test_nonfinite_group_is_incomplete(self):
        null = self.nulls()
        null.loc[0, "effect"] = np.inf
        _, consensus, receipt = self.compute(null)
        self.assertEqual(consensus.to_dict(), {"1": 1})
        self.assertEqual(receipt["null_group_count_distribution"]["8"], 1)

    def test_publication_depth_requires_all_requested_nulls(self):
        with self.assertRaisesRegex(ValueError, "requires 1000 complete"):
            self.compute(self.nulls(999), requested=1000)
        _, consensus, receipt = self.compute(self.nulls(1000), requested=1000)
        self.assertEqual(len(consensus), 1000)
        self.assertTrue(receipt["publication_depth_passed"])

    def test_missing_null_group_cannot_be_replaced_by_supportive_group(self):
        null = self.nulls(2)
        null.loc[0, "display_group"] = "Neural / glial cells"
        _, consensus, receipt = self.compute(null)
        self.assertEqual(consensus.index.tolist(), ["1"])
        self.assertEqual(receipt["n_null_incomplete"], 1)

    def test_summary_uses_complete_nulls_and_correct_effect_description(self):
        real = pd.DataFrame([score_row(i, 2) for i in range(11)])
        null = pd.DataFrame([score_row(i, value, null_id)
                             for null_id, value in (("a", 0), ("b", 1), ("c", 2)) for i in range(11)])
        real_path, null_path = self.root / "real.tsv", self.root / "null.tsv"
        real.to_csv(real_path, sep="\t", index=False)
        null.to_csv(null_path, sep="\t", index=False)
        pd.DataFrame({"null_id": ["a", "b", "c"]}).to_csv(
            self.root / "matched_deletion_nulls.tsv", sep="\t", index=False)
        catalog = small_catalog()
        with patch("worker.brain9.registry", return_value=catalog):
            summary = worker.compute_from_scores(
                payload={"variant_group_id": "TEST_del3", "gene_symbol": "TEST", "ref": "AC", "alt": "A", "null_depth": 3},
                v04_pipeline_dir=self.root, real_scores=real_path, null_scores=null_path,
                results_dir=self.root / "results",
            )
        self.assertEqual(summary["n_real_brain_groups"], 9)
        self.assertEqual(summary["n_null_consensus"], 3)
        self.assertEqual(summary["effect_definition"], "GeneMaskLFC score minus trackwise matched-null median")
        self.assertEqual(summary["observed_direction_one_sided_status"], "exploratory_not_prespecified")
        self.assertAlmostEqual(summary["empirical_p_two_sided"], .75)
        self.assertAlmostEqual(summary["real_consensus_delta"], 1)
        self.assertEqual(summary["primary_brain_coverage"]["n_null_incomplete"], 0)


if __name__ == "__main__":
    unittest.main()
