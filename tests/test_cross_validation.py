"""Release acceptance must reject deliberate scientific-output mismatches."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from scripts.cross_validation_checks import (
    cohort_reference_passed, numeric_comparison, single_reference_passed, validate_recorded_reports,
)
from scripts.compare_frontal_cortex import build_report, main


class NumericAcceptanceTests(unittest.TestCase):
    def test_nonfinite_mismatch_never_passes(self):
        for left, right in (([np.inf], [1.0]), ([np.inf], [np.inf]),
                            ([np.inf], [-np.inf]), ([np.nan], [1.0]),
                            ([np.nan], [np.nan]), ([], [])):
            with self.subTest(left=left, right=right):
                check = numeric_comparison(np.array(left), np.array(right), atol=1e-15)
                self.assertFalse(check["equivalent_at_serialization_tolerance"])

    def test_shape_mismatch_is_structured(self):
        check = numeric_comparison(np.zeros(2), np.zeros(3))
        self.assertFalse(check["same_shape"])
        self.assertFalse(check["equivalent_at_serialization_tolerance"])
        self.assertIsNone(check["max_abs_difference"])

    def test_finite_subtraction_overflow_is_a_serializable_failure(self):
        check = numeric_comparison(np.array([1e308]), np.array([-1e308]), atol=1e-15)
        self.assertFalse(check["equivalent_at_serialization_tolerance"])
        self.assertIsNone(check["max_abs_difference"])
        json.dumps(check, allow_nan=False)

    def test_matching_aligned_nan_requires_explicit_opt_in(self):
        values = np.array([0.25, np.nan])
        self.assertFalse(numeric_comparison(values, values)["equivalent_at_serialization_tolerance"])
        self.assertTrue(numeric_comparison(values, values, allow_matching_nan=True)["equivalent_at_serialization_tolerance"])

    def test_tolerance_does_not_hide_exact_flag_or_material_mismatch(self):
        check = numeric_comparison(np.array([0.1]), np.array([0.1 + 2e-16]), atol=1e-15)
        self.assertFalse(check["exact"])
        self.assertTrue(check["equivalent_at_serialization_tolerance"])
        check = numeric_comparison(np.array([0.1]), np.array([0.1 + 1e-8]), atol=1e-15)
        self.assertFalse(check["equivalent_at_serialization_tolerance"])

    def test_single_reference_failure_prevents_success(self):
        reference = {
            "track_values": {name: {"exact": True, "changed_tracks": 0, "max_abs_difference": 0}
                             for name in ("raw_score", "null_median", "effect")},
            "summary": {name: {"exact": True, "difference": 0, "fresh": 0.1, "v0_20": 0.1}
                        for name in ("real_consensus_delta", "empirical_p_two_sided", "empirical_p_observed_direction")},
        }
        contexts = [{"fresh_vs_sealed_v0_20": reference}]
        self.assertTrue(single_reference_passed(contexts))
        reference["track_values"]["effect"]["exact"] = False
        self.assertFalse(single_reference_passed(contexts))
        self.assertFalse(single_reference_passed([]))

    def test_cohort_reference_and_cosine_failure_prevent_success(self):
        reference = {"matrix": {"exact": True, "max_abs_difference": 0},
                     "statistics": {str(i): {"exact": True, "max_abs_difference": 0} for i in range(5)},
                     "cosine": {"equivalent_at_absolute_tolerance": True, "max_abs_difference": 2.22e-16}}
        self.assertTrue(cohort_reference_passed(reference))
        changed = copy.deepcopy(reference)
        changed["matrix"]["exact"] = False
        self.assertFalse(cohort_reference_passed(changed))
        reference["cosine"]["max_abs_difference"] = 1e-5
        self.assertFalse(cohort_reference_passed(reference))


class CurveToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.fresh, self.sealed = root / "fresh", root / "sealed"
        self.output = root / "comparison.json"
        self.status = {
            "status": "ok", "interval": {"chromosome": "chr16", "start": 10, "end": 14},
            "ontology_terms": ["UBERON:0001870"], "track_idx": 0,
            "track_metadata": {"name": "UBERON:0001870 gtex Brain_Cortex polyA plus RNA-seq",
                "strand": ".", "Assay title": "polyA plus RNA-seq", "ontology_curie": "UBERON:0001870",
                "biosample_name": "frontal cortex", "biosample_type": "tissue", "biosample_life_stage": "adult",
                "gtex_tissue": "Brain_Cortex", "data_source": "gtex", "endedness": "paired",
                "genetically_modified": False},
        }
        for context, figure in (("rbfox1_16kb", "Figure2_RBFOX1_16kb"), ("ptchd1_1mb", "Figure4_PTCHD1_1Mb")):
            fresh_dir = self.fresh / "contexts" / context / "results"
            old_dir = self.sealed / figure / "data/curves/raw_and_aligned"
            fresh_dir.mkdir(parents=True)
            old_dir.mkdir(parents=True)
            (fresh_dir / "frontal_cortex_prediction_status.json").write_text(json.dumps(self.status))
            old_status_name = "prediction_status.json" if context == "ptchd1_1mb" else "frontal_cortex_prediction_status.json"
            (old_dir / old_status_name).write_text(json.dumps(self.status))
            for kind in ("raw", "aligned"):
                filename = "frontal_cortex_prediction_raw.tsv" if kind == "raw" else "frontal_cortex_prediction.tsv"
                alternate = np.array([0.1, 0.2, 0.3, 0.4])
                if kind == "aligned":
                    alternate[1] = np.nan
                frame = pd.DataFrame({"position": np.arange(10, 14), "ref_prediction": [0.2, 0.3, 0.4, 0.5],
                                      "alt_prediction": alternate})
                frame.to_csv(fresh_dir / filename, sep="\t", index=False)
                if context == "rbfox1_16kb":
                    frame.to_csv(old_dir / filename, sep="\t", index=False)
                elif kind == "raw":
                    np.savez(old_dir / "returned_rna_predictions.npz", interval_start=10, interval_end=14,
                             reference=frame["ref_prediction"].to_numpy()[:, None], alternate=alternate[:, None])
                else:
                    np.savez(old_dir / "selected_aligned_prediction.npz", position=frame["position"].to_numpy(),
                             reference=frame["ref_prediction"].to_numpy(), alternate=alternate)

    def arguments(self):
        return ["--fresh-root", str(self.fresh), "--sealed-root", str(self.sealed), "--output", str(self.output)]

    def test_both_curve_formats_pass_and_report_no_local_paths(self):
        report = build_report(self.fresh, self.sealed)
        self.assertEqual(report["status"], "passed")
        self.assertNotIn(self.tmp.name, json.dumps(report))

    def test_material_curve_mismatch_writes_failure_and_exits_nonzero(self):
        path = self.fresh / "contexts/ptchd1_1mb/results/frontal_cortex_prediction.tsv"
        frame = pd.read_csv(path, sep="\t")
        frame.loc[0, "ref_prediction"] += 0.01
        frame.to_csv(path, sep="\t", index=False)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(self.arguments()), 1)
        self.assertEqual(json.loads(self.output.read_text())["status"], "failed")

    def test_shorter_curve_writes_failure_without_key_error(self):
        path = self.fresh / "contexts/rbfox1_16kb/results/frontal_cortex_prediction.tsv"
        frame = pd.read_csv(path, sep="\t").iloc[:-1]
        frame.to_csv(path, sep="\t", index=False)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(self.arguments()), 1)
        report = json.loads(self.output.read_text())
        self.assertFalse(report["contexts"]["rbfox1_16kb"]["aligned"]["position"]["same_shape"])

    def test_whole_brain_track_is_rejected(self):
        path = self.fresh / "contexts/rbfox1_16kb/results/frontal_cortex_prediction_status.json"
        self.status["track_metadata"]["ontology_curie"] = "UBERON:0000955"
        path.write_text(json.dumps(self.status))
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(self.arguments()), 1)

    def test_existing_report_is_preserved(self):
        self.output.write_text("preserve")
        with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            main(self.arguments())
        self.assertEqual(self.output.read_text(), "preserve")


class RecordedReportTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / "docs/verification/v024"
        self.reports = [json.loads((root / name).read_text()) for name in
                        ("all_contexts_report.json", "cohort_cross_validation_report.json", "curve_cross_validation_report.json")]

    def test_published_report_facts_meet_strict_acceptance(self):
        self.assertEqual(validate_recorded_reports(*self.reports)["status"], "passed")

    def test_optimistic_top_level_status_cannot_hide_changed_score(self):
        self.reports[0]["contexts"][0]["fresh_vs_sealed_v0_20"]["track_values"]["effect"].update(exact=False, changed_tracks=1, max_abs_difference=0.1)
        result = validate_recorded_reports(*self.reports)
        self.assertEqual(result["status"], "failed")
        self.assertIn("single:sealed_reference_mismatch", result["errors"])

    def test_optimistic_top_level_status_cannot_hide_material_cosine_change(self):
        self.reports[1]["fresh_vs_sealed_v0_20"]["cosine"]["max_abs_difference"] = 0.01
        self.assertEqual(validate_recorded_reports(*self.reports)["status"], "failed")

    def test_nonfinite_report_value_is_rejected(self):
        self.reports[2]["contexts"]["ptchd1_1mb"]["raw"]["ref_prediction"]["max_abs_difference"] = float("inf")
        self.assertEqual(validate_recorded_reports(*self.reports)["status"], "failed")

    def test_missing_context_is_rejected(self):
        self.reports[0]["contexts"].pop()
        self.assertEqual(validate_recorded_reports(*self.reports)["status"], "failed")


if __name__ == "__main__":
    unittest.main()
