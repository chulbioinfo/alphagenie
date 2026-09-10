from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from worker import run_single_variant_job as worker
from brain9_fixtures import small_catalog, score_row


class NullSourceExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data = self.root / "data"
        self.data.mkdir()
        self.results = self.root / "results"
        self.payload = {
            "variant_group_id": "TEST_del3", "gene_symbol": "TEST",
            "chrom": "chr1", "pos1": 100, "ref": "TCCG", "alt": "T",
            "null_depth": 1000,
        }

    def score_row(self, group_index, value, null_id=None):
        return score_row(group_index, value, null_id)

    def score_fixture(self, count):
        real = pd.DataFrame([self.score_row(g, 0.42 + 0.031 * g) for g in range(11)])
        null = pd.DataFrame([
            self.score_row(g, (i - count / 2) / count + 0.031 * g, f"null_{i:04d}")
            for i in range(count) for g in range(11)
        ])
        real_path, null_path = self.data / "real_scores.tsv", self.data / "null_scores.tsv"
        real.to_csv(real_path, sep="\t", index=False)
        null.to_csv(null_path, sep="\t", index=False)
        return real_path, null_path

    def summarize(self, real_path, null_path):
        catalog = small_catalog()
        with patch("worker.brain9.registry", return_value=catalog), patch.object(
            worker.np.random, "default_rng", side_effect=AssertionError("exports must not generate nulls")
        ):
            return worker.compute_from_scores(
                payload=self.payload, v04_pipeline_dir=self.root,
                real_scores=real_path, null_scores=null_path, results_dir=self.results,
            )

    def test_thousand_null_exports_reproduce_p_and_preserve_original_design(self):
        real_path, null_path = self.score_fixture(1000)
        design = self.data / "matched_deletion_nulls.tsv"
        pd.DataFrame([
            {"null_id": f"null_{i:04d}", "variant_group_id": "TEST_del3", "chrom": "chr1",
             "pos1": 1000 + i, "ref": "TCCG", "alt": "T", "match_stage": "gc10"}
            for i in range(1000)
        ]).to_csv(design, sep="\t", index=False)
        original_bytes = {p: p.read_bytes() for p in (real_path, null_path, design)}
        summary = self.summarize(real_path, null_path)
        consensus = pd.read_csv(self.results / "null_consensus.tsv", sep="\t", float_precision="round_trip")
        groups = pd.read_csv(self.results / "null_group_medians.tsv", sep="\t", float_precision="round_trip")
        self.assertEqual(consensus.columns.tolist(), ["null_id", "consensus_effect"])
        self.assertEqual(groups.columns.tolist(), ["null_id", *worker.BRAIN_TISSUE_GROUPS])
        self.assertEqual(len(consensus), 1000)
        self.assertEqual(len(groups), 1000)
        self.assertEqual(consensus["null_id"].tolist(), groups["null_id"].tolist())
        np.testing.assert_array_equal(
            consensus["consensus_effect"].to_numpy(),
            groups[list(worker.BRAIN_TISSUE_GROUPS)].median(axis=1).to_numpy(),
        )
        values = consensus["consensus_effect"].to_numpy()
        center = np.median(values)
        observed = summary["real_consensus_delta"] - center
        p_two = (1 + np.sum(np.abs(values - center) >= abs(observed))) / (1 + len(values))
        p_obs = (1 + np.sum(values - center >= observed)) / (1 + len(values))
        self.assertEqual(p_two, summary["empirical_p_two_sided"])
        self.assertEqual(p_obs, summary["empirical_p_observed_direction"])
        self.assertEqual(center, summary["null_consensus_median"])
        self.assertEqual((self.results / "matched_null_design.tsv").read_bytes(), original_bytes[design])
        self.assertTrue(summary["matched_null_design_available"])
        self.assertEqual(set(summary["reproducibility_source_files"]), {"null_consensus", "null_group_medians", "matched_null_design", "classification_audit", "classification_tracks"})
        for path, content in original_bytes.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).digest(), hashlib.sha256(content).digest())

    def test_missing_design_is_explicit_and_does_not_copy_another_variant_class(self):
        real_path, null_path = self.score_fixture(3)
        self.payload["null_depth"] = 3
        (self.data / "matched_insertion_nulls.tsv").write_text("wrong class\n")
        with self.assertRaisesRegex(ValueError, "requires its original matched-null design"):
            self.summarize(real_path, null_path)
        self.assertFalse((self.results / "matched_null_design.tsv").exists())

    def test_design_kind_selection_and_missing_source_preserves_previous_export(self):
        for ref, alt, kind in (("T", "TCCG", "insertion"), ("A", "G", "substitution"), ("TCCG", "T", "deletion")):
            source = self.data / f"matched_{kind}_nulls.tsv"
            source.write_text(f"null_id\tclass\nexample\t{kind}\n")
            destination = worker.copy_matched_null_design(
                {**self.payload, "ref": ref, "alt": alt}, data_dir=self.data, results_dir=self.results,
            )
            self.assertEqual(destination.read_bytes(), source.read_bytes())
        missing_data = self.root / "missing-data"
        self.assertIsNone(worker.copy_matched_null_design(self.payload, data_dir=missing_data, results_dir=self.results))
        self.assertFalse((self.results / "matched_null_design.tsv").exists())
        self.assertEqual(len(list(self.results.glob("matched_null_design.tsv.previous-*"))), 1)

    def test_frozen_demo_copies_existing_exports_and_marks_legacy_missing_sources(self):
        frozen = self.root / "frozen"
        frozen.mkdir()
        (frozen / "source_table.tsv").write_text("effect\n1\n")
        (frozen / "group_summary.tsv").write_text("median_effect\n1\n")
        (frozen / "consensus_summary.json").write_text(json.dumps({"variant_group_id": "TEST_del3"}))
        names = ("null_consensus.tsv", "null_group_medians.tsv", "matched_null_design.tsv")
        for name in names:
            (frozen / name).write_text(f"example\n{name}\n")
        spec = {"demo_cache_dir": frozen, "publication_release_id": "frozen-test"}
        with patch.object(worker, "validate_demo_payload", return_value=spec):
            summary = worker.load_demo_outputs(self.payload, self.root / "legacy", self.results)
        for name in names:
            self.assertEqual((self.results / name).read_bytes(), (frozen / name).read_bytes())
        self.assertTrue(summary["matched_null_design_available"])
        self.assertEqual(summary["unavailable_reproducibility_source_files"], [])
        old_frozen = self.root / "legacy-frozen"
        old_frozen.mkdir()
        for name in ("source_table.tsv", "group_summary.tsv", "consensus_summary.json"):
            (old_frozen / name).write_bytes((frozen / name).read_bytes())
        with patch.object(worker, "validate_demo_payload", return_value={"demo_cache_dir": old_frozen}):
            legacy = worker.load_demo_outputs(self.payload, self.root / "legacy", self.results)
        self.assertFalse(legacy["matched_null_design_available"])
        self.assertEqual(legacy["reproducibility_source_files"], {})
        self.assertEqual(legacy["unavailable_reproducibility_source_files"], list(names))
        for name in names:
            self.assertFalse((self.results / name).exists())
            self.assertEqual(len(list(self.results.glob(f"{name}.previous-*"))), 1)


if __name__ == "__main__":
    unittest.main()
