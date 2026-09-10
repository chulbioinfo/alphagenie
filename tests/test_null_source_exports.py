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

    def score_fixture(self, count, null_ids=None):
        null_ids = [f"null_{i:04d}" for i in range(count)] if null_ids is None else null_ids
        real = pd.DataFrame([self.score_row(g, 0.42 + 0.031 * g) for g in range(11)])
        null = pd.DataFrame([
            self.score_row(g, (i - count / 2) / count + 0.031 * g, null_ids[i])
            for i in range(count) for g in range(11)
        ])
        real_path, null_path = self.data / "real_scores.tsv", self.data / "null_scores.tsv"
        real.to_csv(real_path, sep="\t", index=False)
        null.to_csv(null_path, sep="\t", index=False)
        return real_path, null_path

    def design_fixture(self, count, kind="deletion", null_ids=None, id_schema="native"):
        null_ids = [f"null_{i:04d}" for i in range(count)] if null_ids is None else null_ids
        ref, alt = self.payload["ref"], self.payload["alt"]
        rows = []
        for i in range(count):
            row = {
                "null_variant_id": null_ids[i],
                "matched_real_variant_id": f"chr1:100:{ref}>{alt}",
                "matched_real_variant_group_id": self.payload["variant_group_id"],
                "gene_symbol": "TEST", "target_gene": "TEST", "chrom": "chr1",
                "pos_1based": 1000 + i, "ref_normalized": ref, "alt_normalized": alt,
                "sequence_phase": ref[1:] if kind == "deletion" else ref,
                "tss_distance_bin": "same_fixed_1Mb_interval",
                "promoter_orientation": "matched_real_promoter_interval", "gc_decile": "10",
                "cpg_overlap": "not_assessed_fixed_interval",
                "mappability_bin": "not_assessed_fixed_interval", "exclusion_flags": "",
                "matching_status": "matched", "gc_fraction": 1.0,
                "fixed_interval": "chr1:0-1048576", "sampling_stage": "gc10",
            }
            if kind == "deletion":
                row["deletion_length"] = len(ref) - len(alt)
            elif kind == "insertion":
                row.update(insertion_length=len(alt) - len(ref), inserted_sequence=alt[1:],
                           sampling_stage="same_insert_fixed_interval")
            else:
                row.update(substitution_length=len(ref), edit_offsets="0",
                           representation="normalized", sampling_stage="gc10_fixed_interval")
            if id_schema in {"alias", "both"}:
                row["null_id"] = null_ids[i]
            if id_schema == "alias":
                del row["null_variant_id"]
            rows.append(row)
        design = self.data / f"matched_{kind}_nulls.tsv"
        pd.DataFrame(rows).to_csv(design, sep="\t", index=False)
        return design

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
        design = self.design_fixture(1000)
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

    def test_ten_null_native_designs_and_compatibility_aliases(self):
        null_ids = [f"{i:04d}" for i in range(10)]
        self.payload["null_depth"] = 10
        for kind, ref, alt in (("deletion", "TCCG", "T"),
                               ("insertion", "T", "TCCG"),
                               ("substitution", "A", "G")):
            for id_schema in ("native", "alias", "both"):
                with self.subTest(kind=kind, id_schema=id_schema):
                    self.payload.update(ref=ref, alt=alt)
                    self.results = self.root / f"results-{kind}-{id_schema}"
                    real_path, null_path = self.score_fixture(10, null_ids)
                    design = self.design_fixture(10, kind, null_ids, id_schema)
                    original_bytes = {p: p.read_bytes() for p in (real_path, null_path, design)}
                    summary = self.summarize(real_path, null_path)
                    self.assertEqual(summary["n_null_consensus"], 10)
                    self.assertTrue(summary["matched_null_design_available"])
                    audit = json.loads((self.results / "classification_audit.json").read_text())
                    self.assertTrue(audit["matched_null_design_ids_checked"])
                    for name in ("null_consensus.tsv", "null_group_medians.tsv"):
                        exported = pd.read_csv(self.results / name, sep="\t", dtype={"null_id": str})
                        self.assertEqual(exported["null_id"].tolist(), null_ids)
                    self.assertEqual((self.results / "matched_null_design.tsv").read_bytes(),
                                     original_bytes[design])
                    for path, content in original_bytes.items():
                        self.assertEqual(path.read_bytes(), content)

    def test_design_reader_preserves_literal_ids_and_source_bytes(self):
        null_ids = ["0007", "7", "NA", "N/A", "null", "nan", "1e3", "  spaced  "]
        for id_schema in ("native", "alias", "both"):
            with self.subTest(id_schema=id_schema):
                design = self.design_fixture(len(null_ids), null_ids=null_ids, id_schema=id_schema)
                original = design.read_bytes()
                self.assertEqual(worker.read_matched_null_ids(design), null_ids)
                self.assertEqual(design.read_bytes(), original)

    def test_literal_null_ids_survive_score_loading_and_summary_exports(self):
        null_ids = ["0007", "7", "NA", "N/A", "null", "nan", "1e3", "id8", "id9", "id10"]
        self.payload["null_depth"] = len(null_ids)
        real_path, null_path = self.score_fixture(len(null_ids), null_ids)
        design = self.design_fixture(len(null_ids), null_ids=null_ids)
        original = design.read_bytes()
        summary = self.summarize(real_path, null_path)
        self.assertEqual(summary["n_null_consensus"], len(null_ids))
        for name in ("null_consensus.tsv", "null_group_medians.tsv"):
            exported = pd.read_csv(self.results / name, sep="\t", dtype={"null_id": str}, keep_default_na=False)
            self.assertEqual(exported["null_id"].tolist(), sorted(null_ids))
        self.assertEqual((self.results / "matched_null_design.tsv").read_bytes(), original)

    def test_design_reader_rejects_empty_and_blank_ids(self):
        design = self.data / "matched_deletion_nulls.tsv"
        design.write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "missing null IDs"):
            worker.read_matched_null_ids(design)
        self.assertEqual(design.read_bytes(), b"")
        for id_column in ("null_variant_id", "null_id"):
            for rows in ("", "\tmatched\n", "   \tmatched\n", '"\t"\tmatched\n'):
                with self.subTest(id_column=id_column, rows=rows):
                    design.write_text(f"{id_column}\tmatching_status\n{rows}")
                    original = design.read_bytes()
                    with self.assertRaisesRegex(ValueError, "missing null IDs"):
                        worker.read_matched_null_ids(design)
                    self.assertEqual(design.read_bytes(), original)

    def test_ten_null_invalid_designs_fail_before_consensus_exports(self):
        self.payload["null_depth"] = 10
        real_path, null_path = self.score_fixture(10)
        cases = ("no_id", "blank_native", "blank_alias", "duplicate_native", "duplicate_alias",
                 "conflicting_columns", "blank_dual_alias", "mismatched_score_ids", "wrong_design_count")
        for case in cases:
            with self.subTest(case=case):
                self.results = self.root / f"results-{case}"
                id_schema = "alias" if case.endswith("_alias") and case != "blank_dual_alias" else "native"
                if case in {"conflicting_columns", "blank_dual_alias"}:
                    id_schema = "both"
                design = self.design_fixture(10, id_schema=id_schema)
                frame = pd.read_csv(design, sep="\t", dtype=str, keep_default_na=False)
                id_column = "null_id" if id_schema == "alias" else "null_variant_id"
                expected_error = "missing null IDs"
                if case == "no_id":
                    frame = frame.drop(columns=id_column)
                elif case.startswith("blank"):
                    frame.loc[0, "null_id" if case == "blank_dual_alias" else id_column] = "   "
                elif case.startswith("duplicate"):
                    frame.loc[1, id_column] = frame.loc[0, id_column]
                    expected_error = "duplicate null IDs"
                elif case == "conflicting_columns":
                    frame["null_id"] = frame["null_id"].iloc[::-1].tolist()
                    expected_error = "conflicting null ID columns"
                elif case == "mismatched_score_ids":
                    frame.loc[0, id_column] = "unscored_null"
                    expected_error = "scored null IDs differ from the sampled matched-null design"
                else:
                    frame = frame.iloc[:-1]
                    expected_error = "scored null IDs differ from the sampled matched-null design"
                frame.to_csv(design, sep="\t", index=False)
                original_bytes = {p: p.read_bytes() for p in (real_path, null_path, design)}
                with self.assertRaisesRegex(ValueError, expected_error):
                    self.summarize(real_path, null_path)
                for name in ("null_consensus.tsv", "null_group_medians.tsv", "consensus_summary.json"):
                    self.assertFalse((self.results / name).exists())
                for path, content in original_bytes.items():
                    self.assertEqual(path.read_bytes(), content)

    def test_native_design_does_not_relax_requested_null_count(self):
        self.payload["null_depth"] = 10
        real_path, null_path = self.score_fixture(9)
        self.design_fixture(9)
        with self.assertRaisesRegex(ValueError, "requires 10 complete nulls; observed 9"):
            self.summarize(real_path, null_path)
        audit = json.loads((self.results / "classification_audit.json").read_text())
        self.assertEqual(audit["status"], "failed")
        self.assertFalse((self.results / "null_consensus.tsv").exists())

    def test_native_design_does_not_relax_complete_tracks_or_finite_scores(self):
        self.payload["null_depth"] = 10
        self.design_fixture(10)
        for case, expected_error in (
            ("missing_track", "every null must contain the same complete track set"),
            ("nonfinite_score", "null contains nonfinite raw scores"),
        ):
            with self.subTest(case=case):
                self.results = self.root / f"results-{case}"
                real_path, null_path = self.score_fixture(10)
                null = pd.read_csv(null_path, sep="\t")
                if case == "missing_track":
                    null = null.iloc[:-1]
                else:
                    null.loc[0, "raw_score"] = np.inf
                null.to_csv(null_path, sep="\t", index=False)
                with self.assertRaisesRegex(ValueError, expected_error):
                    self.summarize(real_path, null_path)
                audit = json.loads((self.results / "classification_audit.json").read_text())
                self.assertEqual(audit["status"], "failed")
                self.assertFalse((self.results / "null_consensus.tsv").exists())

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
