"""Offline regression against v0.20 raw nulls; no API client is created."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from brain9_fixtures import small_catalog, frames
from worker import brain9
from worker import run_single_variant_job as single
from worker import run_multi_variant_job as multi


class Brain9ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.catalog = small_catalog()

    def compute(self, real, null, depth=3, ids=None):
        with patch.object(brain9, "registry", return_value=self.catalog):
            return brain9.canonicalize_scores(real, null, requested_null_depth=depth,
                                             audit_out=self.root / "classification_audit.json", expected_null_ids=ids)

    def test_full_catalog_counts_and_sensitive_material_assignments(self):
        catalog = brain9.registry()
        self.assertEqual([sum(v["display_group"] == group for v in catalog.values())
                          for group, _ in brain9.FULL_GROUP_ORDER], [4, 1, 3, 1, 1, 1, 2, 1, 7, 153, 197])
        for item in catalog.values():
            if item["included_in_brain9"]:
                self.assertEqual(item["biosample_type"], "tissue")
                self.assertEqual(item["biosample_life_stage"], "embryonic" if item["display_group"] == "Embryo" else "adult")
            if item["gtex_tissue"] in {"Cells_Cultured_fibroblasts", "Cells_EBV-transformed_lymphocytes"}:
                self.assertEqual(item["display_group"], "Cells & cell lines")
            if item["ontology_curie"] in {"UBERON:0002240", "UBERON:0006469", "UBERON:0000007"}:
                self.assertEqual(item["display_group"], "Non-brain tissues")
            if item["biosample_type"] != "tissue" and item["biosample_life_stage"] == "embryonic":
                self.assertEqual(item["display_group"], "Cells & cell lines")

    def test_unknown_track_and_metadata_drift_fail_with_audit(self):
        for field, value in (("track_name", "unreviewed"), ("biosample_life_stage", "mixed_adult_embryonic"),
                             ("biosample_type", "cell_line"), ("gtex_tissue", "Changed_tissue")):
            for which in (0, 1):
                with self.subTest(field=field, source=which):
                    real, null = frames()
                    (real, null)[which].loc[0, field] = value
                    with self.assertRaisesRegex(ValueError, "catalog is unknown|metadata changed"):
                        self.compute(real, null)
                    self.assertEqual(json.loads((self.root / "classification_audit.json").read_text())["status"], "failed")
                    self.assertTrue((self.root / "classification_audit.tsv").is_file())

    def test_missing_track_within_same_group_cannot_change_null_composition(self):
        real, null = frames()
        with self.assertRaisesRegex(ValueError, "same complete track set"):
            self.compute(real, null.iloc[1:])
        with self.assertRaisesRegex(ValueError, "track membership"):
            self.compute(real.iloc[1:], null)

    def test_null_identity_depth_nonfinite_and_required_metadata_fail(self):
        for mutate, message in (
            (lambda r, n: (r, n.assign(raw_score=np.nan)), "nonfinite"),
            (lambda r, n: (r, n.assign(null_id=None)), "missing null ID"),
            (lambda r, n: (r.drop(columns="biosample_type"), n), "required columns"),
        ):
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    self.compute(*mutate(*frames()))
        with self.assertRaisesRegex(ValueError, "requires 4 complete"):
            self.compute(*frames(), depth=4)
        with self.assertRaisesRegex(ValueError, "sampled matched-null design"):
            self.compute(*frames(), ids=["0", "1", "different"])

    def test_duplicate_null_rows_are_collapsed_before_track_centering(self):
        real, null = frames()
        # Overweight one null in the raw file. Canonical centering gives median
        # [0,1,100] = 1, not the pooled-row median 100.
        null.loc[(null.null_id == "2") & (null.track_name == null.iloc[0].track_name), "raw_score"] = 100
        repeated = null.loc[(null.null_id == "2") & (null.track_name == null.iloc[0].track_name)]
        null = pd.concat([null, *([repeated] * 50)], ignore_index=True)
        real, canonical, receipt = self.compute(real, null)
        self.assertTrue((real.null_median == 1).all())
        self.assertEqual(len(canonical), 33)
        self.assertEqual(receipt["status"], "passed")

    def test_display_pools_do_not_change_primary_consensus(self):
        real, null = frames()
        real.loc[9:, "raw_score"] = 1000000
        null.loc[null.index % 11 >= 9, "raw_score"] = -1000000
        real, null, _ = self.compute(real, null)
        summary = real.groupby("display_group")["effect"].median().rename("median_effect").reset_index()
        values, distribution, _ = single.complete_primary_brain_consensus(
            summary, null, all_null_ids=["0", "1", "2"], requested_null_depth=3,
            coverage_out=self.root / "coverage.json")
        np.testing.assert_array_equal(values, np.ones(9))
        np.testing.assert_array_equal(distribution, [-1, 0, 1])

    def test_cosine_needs_nine_finite_features_and_keeps_zero_norm_undefined(self):
        for a, b in (([1]*8, [1]*9), ([1]*8+[None], [1]*9), ([1]*8+[np.inf], [1]*9)):
            with self.assertRaisesRegex(ValueError, "all nine finite"):
                multi.cosine(a, b)
        self.assertIsNone(multi.cosine([0]*9, [1]*9)[0])
        self.assertEqual(multi.cosine([1]*9, [-1]*9), (-1, 0, 9))


class Brain9GoldenTests(unittest.TestCase):
    def test_complete_cohort_export_retains_eleven_columns_and_nine_feature_statistics(self):
        path = brain9.ROOT / "ccg17"
        data = json.loads((path / "payload.json").read_text())
        source = pd.read_csv(path / "source_table.tsv", sep="\t", float_precision="round_trip")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            items = []
            for ranking in data["ranking"]:
                rows = source[source.variant_group_id == ranking["variant_group_id"]].copy()
                groups = rows.groupby("display_group").agg(median_effect=("effect", "median"), n_tracks=("track_key", "nunique")).reset_index()
                items.append({"summary": {**ranking, "classification": brain9.provenance(), "primary_effect_scope": brain9.SCOPE},
                              "group": groups, "source": rows,
                              "job": {"job_id": ranking["variant_group_id"], "job_dir": str(root / ranking["variant_group_id"]), "run_mode": "offline_test"}})
            with patch.object(multi, "make_multi_plot") as plot, patch.object(multi, "write_multi_plot_html"):
                summary = multi.combine_single_results(
                    job_id="offline_test", payload={"rows": data["variant_mapping"], "reference_variant_group_id": "RBFOX1_del3"},
                    single_results=items, results_dir=root)
            exported = pd.read_csv(root / "multi_group_matrix.tsv", sep="\t", float_precision="round_trip")
            self.assertTrue(set(group for group, _ in brain9.FULL_GROUP_ORDER).issubset(exported.columns))
            self.assertEqual(summary["heatmap_groups"], list(brain9.BRAIN_TISSUE_GROUPS))
            self.assertEqual(summary["display_only_groups"], list(brain9.DISPLAY_ONLY_GROUPS))
            self.assertEqual(plot.call_args.kwargs["group_track_counts"]["Embryo"], 7)
            cosine = pd.read_csv(root / "multi_reference_cosine.tsv", sep="\t", float_precision="round_trip")
            self.assertTrue((cosine.n_brain_groups_used == 9).all())
            expected = pd.read_csv(path / "cosine.tsv", sep="\t", float_precision="round_trip")
            np.testing.assert_allclose(cosine.brain_cosine_similarity, expected.brain_cosine_similarity, rtol=0, atol=1e-14)
            q = pd.read_csv(root / "multi_consensus_ranking.tsv", sep="\t", float_precision="round_trip")
            np.testing.assert_allclose(q.bh_fdr_two_sided_multi, [r["bh_fdr_two_sided_multi"] for r in data["ranking"]], rtol=0, atol=1e-16)

    def test_adapter_reproduces_both_full_1000_by_371_raw_null_caches(self):
        catalog = brain9.registry()
        for key in ("rbfox1", "ptchd1"):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as temp:
                path = brain9.ROOT / key
                with np.load(path / "scores.npz", allow_pickle=False) as cached:
                    keys = cached["track_keys"].tolist()
                    real = pd.DataFrame([{field: catalog[k][field] for field in brain9.CLASS_FIELDS} for k in keys])
                    null = pd.concat([real] * 1000, ignore_index=True)
                    real["raw_score"] = cached["real_raw"]
                    null["raw_score"] = cached["null_raw"].reshape(-1)
                    null["null_id"] = np.repeat(cached["null_ids"].astype(str), 371)
                    actual, nulls, receipt = brain9.canonicalize_scores(
                        real, null, requested_null_depth=1000, audit_out=Path(temp) / "classification_audit.json",
                        expected_null_ids=cached["null_ids"].astype(str).tolist())
                    np.testing.assert_array_equal(actual.set_index("track_key").loc[keys, "effect"], cached["real_effect"])
                    np.testing.assert_array_equal(actual.set_index("track_key").loc[keys, "null_median"],
                                                  np.median(cached["null_raw"], axis=0))
                groups = actual.groupby("display_group")["effect"].median().rename("median_effect").reset_index()
                real_groups, distribution, _ = single.complete_primary_brain_consensus(
                    groups, nulls, all_null_ids=sorted(nulls.null_id.unique()), requested_null_depth=1000,
                    coverage_out=Path(temp) / "coverage.json")
                saved = json.loads((path / "payload.json").read_text())["analysis"]
                observed = np.median(real_groups)
                center = np.median(distribution)
                p = (1 + np.sum(np.abs(distribution - center) >= abs(observed - center))) / 1001
                self.assertEqual(observed, saved["real_consensus_delta"])
                self.assertEqual(p, saved["empirical_p_two_sided"])
                self.assertEqual(receipt["observed_null_count"], 1000)
                self.assertEqual(int(actual.included_in_brain9.sum()), 21)

    def test_seventeen_variant_grouping_nulls_bh_and_cosine_match_saved_results(self):
        path = brain9.ROOT / "ccg17"
        statistics = json.loads((path / "statistics.json").read_text())
        source = pd.read_csv(path / "source_table.tsv", sep="\t", float_precision="round_trip")
        catalog = brain9.registry()
        source["new_group"] = source.track_key.map({k: v["display_group"] for k, v in catalog.items()})
        self.assertFalse(source.new_group.isna().any())
        source["effect"] = source.raw_score - source.null_median
        matrix = source.groupby(["run_id", "new_group"])["effect"].median().unstack()
        pvalues, tails = [], []
        with np.load(path / "brain9_nulls.npz", allow_pickle=False) as nulls:
            for i, record in enumerate(statistics):
                vector = matrix.loc[record["run_id"], list(brain9.BRAIN_TISSUE_GROUPS)]
                observed = np.median(vector)
                distribution = np.median(nulls["category_nulls"][i], axis=1)
                np.testing.assert_array_equal(distribution, nulls["combined_consensus"][i])
                center = np.median(distribution)
                p = (1 + np.sum(np.abs(distribution-center) >= abs(observed-center)))/1001
                tail = (1 + np.sum(distribution-center >= observed-center if observed >= center
                                   else distribution-center <= observed-center))/1001
                self.assertEqual(observed, record["consensus_effect"])
                self.assertEqual(p, record["p_two_sided"])
                pvalues.append(p)
                tails.append(tail)
        np.testing.assert_allclose(multi.bh_adjust(pvalues), [s["q_two_sided"] for s in statistics], rtol=0, atol=1e-16)
        np.testing.assert_allclose(multi.bh_adjust(tails), [s["q_observed_direction"] for s in statistics], rtol=0, atol=1e-16)
        reference = next(s["run_id"] for s in statistics if s["gene_symbol"] == "RBFOX1")
        ref = matrix.loc[reference, list(brain9.BRAIN_TISSUE_GROUPS)].tolist()
        for record in statistics:
            sim, _, n = multi.cosine(matrix.loc[record["run_id"], list(brain9.BRAIN_TISSUE_GROUPS)].tolist(), ref)
            self.assertEqual(n, 9)
            self.assertAlmostEqual(sim, record["cosine_to_RBFOX1"], places=14)


if __name__ == "__main__":
    unittest.main()
