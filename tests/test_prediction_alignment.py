import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from worker.prediction_alignment import align_existing_prediction, align_prediction_frame


def frame(values, start=100):
    return pd.DataFrame({"position": np.arange(start, start + len(values)),
                         "ref_prediction": np.arange(len(values)), "alt_prediction": values})


def variant(pos1=103, ref="T", alt="TAG"):
    return {"chrom": "chr1", "pos1": pos1, "ref": ref, "alt": alt}


class PredictionAlignmentTests(unittest.TestCase):
    def test_insertion_collapses_anchor_and_inserted_segment(self):
        result, meta = align_prediction_frame(frame([10,20,30,999,888,40,50,60]), variant())
        np.testing.assert_allclose(result.alt_prediction, [10,20,999,40,50,60,np.nan,np.nan], equal_nan=True)
        self.assertEqual(meta["net_length_change"], 2)
        self.assertEqual(result.alignment_status.iloc[2], "insertion_anchor_max")
        self.assertEqual(meta["unavailable_boundary_positions"], 2)

    def test_exact_ptchd1_insertion_is_27_bases(self):
        payload = variant(103, "T", "TCGCCGCCGCCGCGGGCGCCGCTGCCGC")
        result, meta = align_prediction_frame(frame(np.arange(80, dtype=float)), payload)
        self.assertEqual(meta["net_length_change"], 27)
        self.assertEqual(result.alt_prediction.iloc[2], 29)
        self.assertEqual(result.alt_prediction.iloc[3], 30)
        self.assertEqual(result.alt_prediction.isna().sum(), 27)

    def test_deletion_zeroes_only_deleted_reference_bases(self):
        result, meta = align_prediction_frame(frame([10,20,30,60,70,80,90,100]), variant(ref="TCCG", alt="T"))
        np.testing.assert_allclose(result.alt_prediction, [10,20,30,0,0,0,60,70])
        self.assertEqual(meta["net_length_change"], -3)
        self.assertEqual(meta["deleted_reference_positions"], 3)

    def test_snv_and_mnv_leave_coordinate_mapping_unchanged(self):
        for ref, alt in [("T", "G"), ("TC", "GA")]:
            raw = frame([10,20,30,40,50])
            result, meta = align_prediction_frame(raw, variant(ref=ref, alt=alt))
            np.testing.assert_array_equal(result.alt_prediction.to_numpy(), raw.alt_prediction.to_numpy())
            self.assertEqual(meta["net_length_change"], 0)

    def test_shared_suffix_and_left_boundary_deletion(self):
        result, meta = align_prediction_frame(frame([10,20,30,40,50]), variant(101, "CCGT", "T"))
        np.testing.assert_array_equal(result.alt_prediction.to_numpy(), [0,0,0,10,20])
        self.assertEqual(meta["common_suffix_bases"], 1)

    def test_right_boundary_insertion_is_unavailable(self):
        result, _ = align_prediction_frame(frame([10,20,30]), variant(103, "T", "TAG"))
        self.assertTrue(np.isnan(result.alt_prediction.iloc[2]))
        self.assertEqual(result.alignment_status.iloc[2], "unavailable_boundary")

    def test_rejects_noncontiguous_positions_and_outside_allele(self):
        raw = frame([10,20,30])
        with self.assertRaises(ValueError):
            align_prediction_frame(raw.iloc[[0,2]], variant())
        with self.assertRaises(ValueError):
            align_prediction_frame(raw, variant(103, "TCCG", "T"))

    def test_offline_upgrade_preserves_inference_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            source = directory / "frontal_cortex_prediction.tsv"
            frame([10,20,30,999,888,40,50,60]).to_csv(source, sep="\t", index=False)
            original_raw = source.read_bytes()
            original_inference = {"inference_started_at": "2026-09-08T14:00:00Z", "inference_completed_at": "2026-09-08T14:00:05Z"}
            status_path = directory / "frontal_cortex_prediction_status.json"
            status_path.write_text(json.dumps({"status": "ok", "inference_provenance": original_inference}))
            status = align_existing_prediction(directory, variant())
            self.assertEqual(status["inference_provenance"], original_inference)
            self.assertEqual((directory / "frontal_cortex_prediction_raw.tsv").read_bytes(), original_raw)
            receipt = status_path.read_bytes()
            aligned = source.read_bytes()
            align_existing_prediction(directory, variant())
            self.assertEqual(source.read_bytes(), aligned)
            self.assertEqual(status_path.read_bytes(), receipt)
            source.write_bytes(aligned + b"corruption")
            with self.assertRaisesRegex(ValueError, "changed"):
                align_existing_prediction(directory, variant())


if __name__ == "__main__":
    unittest.main()
