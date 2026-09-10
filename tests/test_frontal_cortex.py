"""Offline curve-selection, alignment and cache tests; provider calls are mocked."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from alphagenome.data import genome
from alphagenome.models import dna_client
import numpy as np
import pandas as pd

from worker import rna_curve as curve
from worker import run_single_variant_job as worker


class FrontalCortexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.payload = {"variant_group_id": "TEST_snv", "gene_symbol": "TEST", "chrom": "chr1",
                        "pos1": 10000, "ref": "A", "alt": "G", "sequence_length": 16384,
                        "inference_run_epoch": "offline-test-only"}
        self.interval = genome.Interval("chr1", **{k: v for k, v in curve.requested_interval(self.payload).items() if k != "chrom"})
        self.gtf = self.root / "test.gtf"
        self.gtf.write_text('chr1\ttest\tgene\t9900\t10100\t.\t+\t.\tgene_id "TEST.1"; gene_name "TEST";\n'
                            'chr1\ttest\texon\t9900\t10100\t.\t+\t.\tgene_id "TEST.1"; gene_name "TEST"; transcript_id "T1";\n')
        self.spec = dict(curve.TRACK_SPEC)

    def output(self):
        other = {**self.spec, "data_source": "encode", "biosample_life_stage": "embryonic"}
        # Independent channel order is intentional; the biological identity is the same.
        ref = SimpleNamespace(metadata=pd.DataFrame([other, self.spec]), interval=self.interval, resolution=1,
                              values=np.tile([100., 2.], (16384, 1)))
        alt = SimpleNamespace(metadata=pd.DataFrame([self.spec, other]), interval=self.interval, resolution=1,
                              values=np.tile([3., 200.], (16384, 1)))
        return SimpleNamespace(reference=SimpleNamespace(rna_seq=ref), alternate=SimpleNamespace(rna_seq=alt))

    def generate(self, output):
        client = Mock(predict_variant=Mock(return_value=output))
        with patch.dict(os.environ, {"ALPHA_GENOME_API_KEY": "synthetic-offline-only"}), patch.object(
            dna_client, "create", return_value=client
        ):
            status = worker.generate_frontal_cortex_prediction(
                payload=self.payload, prediction_out=self.root / curve.PREDICTION_NAME,
                gene_model_out=self.root / "gene_model.tsv", status_out=self.root / curve.STATUS_NAME,
                gencode_gtf=self.gtf)
        return status, client

    def test_exact_selector_matches_both_saved_webpage_metadata_records(self):
        base = Path(__file__).resolve().parents[1] / "data/manuscript_v020_20260909"
        for key in ("rbfox1", "ptchd1"):
            metadata = json.loads((base / key / "curve_metadata.json").read_text())
            self.assertEqual(curve.normalized_metadata(metadata), curve.TRACK_SPEC)
            self.assertEqual(curve.choose_frontal_cortex_track(pd.DataFrame([metadata], index=[88])), 0)

    def test_rejects_wrong_missing_ambiguous_and_conflicting_metadata(self):
        for field, value in (("ontology_curie", "UBERON:0000955"), ("ontology_curie", "UBERON:0009834"),
                             ("data_source", "encode"), ("gtex_tissue", "Brain_Frontal_Cortex_BA9"),
                             ("biosample_life_stage", "embryonic"), ("biosample_type", "cell_line"),
                             ("Assay title", "total RNA-seq"), ("strand", "+"), ("name", "different")):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                curve.choose_frontal_cortex_track(pd.DataFrame([{**self.spec, field: value}]))
        for records in ([], [self.spec, self.spec], [{k: v for k, v in self.spec.items() if k != "strand"}],
                        [{**self.spec, "track_strand": "-"}]):
            with self.assertRaises(ValueError):
                curve.choose_frontal_cortex_track(pd.DataFrame(records))

    def test_exported_metadata_aliases_select_the_same_track(self):
        row = dict(self.spec)
        row["track_name"] = row.pop("name")
        row["track_strand"] = row.pop("strand")
        self.assertEqual(curve.choose_frontal_cortex_track(pd.DataFrame([row])), 0)

    def test_prediction_requests_cortex_and_pairs_reordered_ref_alt_tracks(self):
        status, client = self.generate(self.output())
        self.assertEqual(client.predict_variant.call_args.kwargs["ontology_terms"], ["UBERON:0001870"])
        self.assertEqual(status["status"], "ok")
        self.assertTrue(curve.selection_matches(status, self.payload))
        self.assertEqual(status["track_selection"]["reference_track_index"], 1)
        self.assertEqual(status["track_selection"]["alternate_track_index"], 0)
        raw = pd.read_csv(self.root / curve.RAW_PREDICTION_NAME, sep="\t")
        self.assertTrue((raw.ref_prediction == 2).all())
        self.assertTrue((raw.alt_prediction == 3).all())
        self.assertEqual(status["visualization_alignment"]["raw_artifact"], curve.RAW_PREDICTION_NAME)
        self.assertFalse((self.root / "whole_brain_prediction.tsv").exists())

    def test_missing_alt_target_does_not_substitute_or_write_a_curve(self):
        output = self.output()
        output.alternate.rna_seq.metadata.loc[0, "biosample_life_stage"] = "embryonic"
        status, _ = self.generate(output)
        self.assertEqual(status["status"], "unavailable")
        self.assertIn("No Whole brain", status["reason"])
        self.assertFalse((self.root / curve.PREDICTION_NAME).exists())

    def test_invalid_resolution_interval_shape_or_nonfinite_values_are_rejected(self):
        for mutation in ("resolution", "interval", "shape", "finite"):
            with self.subTest(mutation=mutation):
                output = self.output()
                alt = output.alternate.rna_seq
                if mutation == "resolution":
                    alt.resolution = 128
                elif mutation == "interval":
                    alt.interval = genome.Interval("chr2", self.interval.start, self.interval.end)
                elif mutation == "shape":
                    alt.values = alt.values[:-1]
                else:
                    alt.values[0, 0] = np.inf
                with self.assertRaises(ValueError):
                    curve.track_pair_to_frame(output.reference.rna_seq, alt, 1, 0)

    def test_whole_brain_cache_key_cannot_match_new_selection(self):
        identity = worker.inference_identity(self.payload, self.gtf)
        key = worker.prediction_cache_key(self.payload, identity=identity)
        # Reproduce the previous selection-key contract without using any old values.
        old = {k: self.payload[k] for k in ("variant_group_id", "gene_symbol", "chrom", "pos1", "ref", "alt", "sequence_length")}
        old.update(target_gene="TEST", inference_identity=identity, output_type="RNA_SEQ",
                   ontology_terms=["UBERON:0000955"], track_selection_version=1, track_alignment_version=1)
        digest = hashlib.sha256(json.dumps(old, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]
        self.assertNotEqual(key, "TEST_snv_" + digest)
        with patch.object(worker, "CURVE_TRACK_SPEC", {**curve.TRACK_SPEC, "strand": "+"}):
            self.assertNotEqual(key, worker.prediction_cache_key(self.payload, identity=identity))

    def test_cache_checks_tissue_variant_and_window_and_preserves_inference_dates(self):
        client = Mock(predict_variant=Mock(return_value=self.output()))
        results = self.root / "results"
        args = dict(payload=self.payload, results_dir=results, cache_root=self.root, gencode_gtf=self.gtf)
        with patch.dict(os.environ, {"ALPHA_GENOME_API_KEY": "synthetic-offline-only"}), patch.object(dna_client, "create", return_value=client):
            first = worker.ensure_frontal_cortex_prediction(**args)
            second = worker.ensure_frontal_cortex_prediction(**args)
        self.assertEqual(first["status"], "ok")
        self.assertEqual(second["cache"], "hit")
        self.assertFalse(second["api_called_this_request"])
        self.assertEqual(first["inference_provenance"], second["inference_provenance"])
        self.assertEqual(client.predict_variant.call_count, 1)
        for field, value in (("ontology_terms", ["UBERON:0000955"]), ("resolution_bp", 128),
                             ("interval", {"chrom": "chr1", "start": 1, "end": 2})):
            self.assertFalse(curve.selection_matches({**first, field: value}, self.payload))
        altered = deepcopy(first)
        altered["visualization_alignment"]["variant"]["ref"] = "T"
        self.assertFalse(curve.selection_matches(altered, self.payload))
        altered = deepcopy(first)
        altered["alternate_track_metadata"]["gtex_tissue"] = "Brain_Frontal_Cortex_BA9"
        self.assertFalse(curve.selection_matches(altered, self.payload))

    def test_failed_refresh_hides_stale_cortex_without_touching_old_whole_brain_file(self):
        results = self.root / "results"
        args = dict(payload=self.payload, results_dir=results, cache_root=self.root, gencode_gtf=self.gtf)
        client = Mock(predict_variant=Mock(return_value=self.output()))
        with patch.dict(os.environ, {"ALPHA_GENOME_API_KEY": "synthetic-offline-only"}), patch.object(dna_client, "create", return_value=client):
            status = worker.ensure_frontal_cortex_prediction(**args)
            self.assertEqual(status["status"], "ok")
            old = results / "whole_brain_prediction.tsv"
            old.write_text("legacy artifact; not a cortex prediction\n")
            client.predict_variant.side_effect = RuntimeError("offline simulated failure")
            failed = worker.ensure_frontal_cortex_prediction(**{**args, "payload": {**self.payload, "force_refresh_predictions": True}})
        self.assertEqual(failed["status"], "failed")
        self.assertFalse((results / curve.PREDICTION_NAME).exists())
        self.assertTrue(list(results.glob(curve.PREDICTION_NAME + ".previous-*")))
        self.assertEqual(old.read_text(), "legacy artifact; not a cortex prediction\n")


if __name__ == "__main__":
    unittest.main()
