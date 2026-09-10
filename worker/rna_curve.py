"""Exact v0.21 manuscript RNA-curve identity; no tissue or assay fallback."""
from __future__ import annotations

import numpy as np
import pandas as pd

SPEC_ID = "frontal_cortex_gtex_brain_cortex_unstranded_v1"
TISSUE_LABEL = "Frontal cortex"
ONTOLOGY = "UBERON:0001870"
PREDICTION_NAME = "frontal_cortex_prediction.tsv"
RAW_PREDICTION_NAME = "frontal_cortex_prediction_raw.tsv"
STATUS_NAME = "frontal_cortex_prediction_status.json"
TRACK_SPEC = {
    "name": "UBERON:0001870 gtex Brain_Cortex polyA plus RNA-seq",
    "ontology_curie": ONTOLOGY,
    "biosample_name": "frontal cortex",
    "biosample_type": "tissue",
    "biosample_life_stage": "adult",
    "data_source": "gtex",
    "gtex_tissue": "Brain_Cortex",
    "Assay title": "polyA plus RNA-seq",
    "strand": ".",
}


def normalized_metadata(row) -> dict[str, str]:
    """Support the SDK's name/strand and exported track_name/track_strand aliases.

    Missing, conflicting or changed identity fields do not match the selector.
    Scientific metadata is not translated or inferred from labels.
    """
    result = {}
    for field in TRACK_SPEC:
        aliases = (field, "track_" + field) if field in {"name", "strand"} else (field,)
        values = [str(row[key]) for key in aliases if key in row and pd.notna(row[key])]
        result[field] = values[0] if values and len(set(values)) == 1 else ""
    return result


def choose_frontal_cortex_track(metadata: pd.DataFrame) -> int:
    """Return the unique positional index, never the DataFrame's index label."""
    if metadata is None or metadata.empty:
        raise ValueError("Frontal cortex RNA track metadata unavailable; no tissue fallback")
    matches = [i for i, row in enumerate(metadata.to_dict("records"))
               if normalized_metadata(row) == TRACK_SPEC]
    if len(matches) != 1:
        raise ValueError("Expected exactly one adult GTEx Brain_Cortex UBERON:0001870 polyA+ unstranded track; "
                         f"found {len(matches)}. No Whole brain, BA9, ENCODE, embryo or strand fallback.")
    return matches[0]


def selection_receipt(ref_metadata, alt_metadata) -> dict:
    ref_index = choose_frontal_cortex_track(ref_metadata)
    alt_index = choose_frontal_cortex_track(alt_metadata)
    return {"spec_id": SPEC_ID, "required_metadata": dict(TRACK_SPEC),
            "reference_track_index": ref_index, "alternate_track_index": alt_index}


def requested_interval(payload) -> dict:
    from alphagenome.data import genome
    variant = genome.Variant(chromosome=str(payload["chrom"]), position=int(payload["pos1"]),
                             reference_bases=str(payload["ref"]).upper(), alternate_bases=str(payload["alt"]).upper())
    interval = variant.reference_interval.resize(int(payload.get("sequence_length", 1_048_576)))
    return {"chrom": interval.chromosome, "start": int(interval.start), "end": int(interval.end)}


def selection_matches(status: dict, payload: dict) -> bool:
    """A hash-valid Whole brain file still cannot satisfy a cortex cache request."""
    selection = status.get("track_selection") or {}
    return (selection.get("spec_id") == SPEC_ID
            and selection.get("required_metadata") == TRACK_SPEC
            and status.get("ontology_terms") == [ONTOLOGY]
            and status.get("interval") == requested_interval(payload)
            and status.get("resolution_bp") == 1
            and status.get("input_sequence_length") == int(payload.get("sequence_length", 1_048_576))
            and (status.get("visualization_alignment") or {}).get("variant") == {
                "chrom": str(payload["chrom"]), "pos1": int(payload["pos1"]),
                "ref": str(payload["ref"]).upper(), "alt": str(payload["alt"]).upper()}
            and normalized_metadata(status.get("track_metadata") or {}) == TRACK_SPEC
            and normalized_metadata(status.get("alternate_track_metadata") or {}) == TRACK_SPEC)


def track_pair_to_frame(ref, alt, ref_index: int, alt_index: int) -> pd.DataFrame:
    """Extract the same biological track independently from REF and ALT outputs."""
    intervals = [(td.interval.chromosome, int(td.interval.start), int(td.interval.end)) for td in (ref, alt)]
    if intervals[0] != intervals[1] or int(ref.resolution) != 1 or int(alt.resolution) != 1:
        raise ValueError("REF/ALT RNA curves require the same interval and 1-bp resolution")
    tracks = []
    for td, index in ((ref, ref_index), (alt, alt_index)):
        values = np.asarray(td.values)
        metadata_count = len(td.metadata)
        if values.ndim == 1 and metadata_count == 1 and index == 0:
            track = values
        elif values.ndim == 2 and values.shape[1] == metadata_count and 0 <= index < metadata_count:
            track = values[:, index]
        else:
            raise ValueError("RNA values and track metadata dimensions are inconsistent")
        if len(track) != intervals[0][2] - intervals[0][1] or not np.isfinite(track).all():
            raise ValueError("RNA curve is nonfinite or does not cover the requested interval")
        tracks.append(track.astype(float))
    return pd.DataFrame({"position": np.arange(intervals[0][1], intervals[0][2]),
                         "ref_prediction": tracks[0], "alt_prediction": tracks[1]})
