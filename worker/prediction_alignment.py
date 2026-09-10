"""Project raw allele-sequence predictions onto reference genomic positions.

This is visualization postprocessing, not a new AlphaGenome inference or the
GeneMaskLFC scorer. Raw predictions are retained unchanged. For pure insertions
we explicitly use the maximum over the left anchor and inserted bases; deleted
reference positions are zero. Unavailable sequence boundaries remain NaN.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any, Mapping

import numpy as np
import pandas as pd

TRACK_ALIGNMENT_VERSION = 1
RAW_PREDICTION_NAME = "frontal_cortex_prediction_raw.tsv"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _variant(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "chrom": str(payload["chrom"]), "pos1": int(payload["pos1"]),
        "ref": str(payload["ref"]).upper(), "alt": str(payload["alt"]).upper(),
    }


def align_prediction_frame(
    frame: pd.DataFrame, payload: Mapping[str, Any]
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Align a contiguous, 1-bp raw ALT frame to its REF coordinate frame."""
    required = {"position", "ref_prediction", "alt_prediction"}
    if not required.issubset(frame.columns) or frame.empty:
        raise ValueError("Alignment requires nonempty position/REF/ALT prediction columns")
    positions = pd.to_numeric(frame["position"], errors="raise").to_numpy()
    if not np.isfinite(positions).all() or not np.equal(positions, np.floor(positions)).all():
        raise ValueError("Prediction positions must be finite integer reference coordinates")
    positions = positions.astype(np.int64)
    if len(positions) > 1 and not np.all(np.diff(positions) == 1):
        raise ValueError("Indel projection currently requires contiguous 1-bp predictions")
    variant = _variant(payload)
    ref, alt = variant["ref"], variant["alt"]
    if not ref or not alt or set(ref + alt) - set("ACGTN"):
        raise ValueError("Alignment requires explicit, nonempty DNA REF and ALT alleles")
    pos0 = variant["pos1"] - 1
    first, end = int(positions[0]), int(positions[-1]) + 1
    if pos0 < first or pos0 + len(ref) > end:
        raise ValueError("The complete reference allele must lie within the prediction frame")

    prefix = 0
    while prefix < min(len(ref), len(alt)) and ref[prefix] == alt[prefix]:
        prefix += 1
    suffix = 0
    while suffix < min(len(ref) - prefix, len(alt) - prefix) and ref[-1-suffix] == alt[-1-suffix]:
        suffix += 1
    ref_edit_length = len(ref) - prefix - suffix
    alt_edit_length = len(alt) - prefix - suffix
    delta = len(alt) - len(ref)
    edit_start = pos0 + prefix
    edit_end = edit_start + ref_edit_length
    raw_alt = pd.to_numeric(frame["alt_prediction"], errors="raise").to_numpy(dtype=float)
    raw_index = np.arange(len(frame), dtype=np.int64)
    statuses = np.full(len(frame), "reference_mapped", dtype=object)
    if delta:
        downstream = positions >= edit_end
        raw_index[downstream] += delta
    available = (raw_index >= 0) & (raw_index < len(raw_alt))
    aligned = np.full(len(frame), np.nan, dtype=float)
    aligned[available] = raw_alt[raw_index[available]]
    statuses[~available] = "unavailable_boundary"
    mapping = raw_index.astype(float)
    mapping[~available] = np.nan

    if ref_edit_length == 0 and alt_edit_length > 0:
        # The insertion has no distinct REF base. Collapse to its shared left
        # anchor when present; preserve the full inserted segment in raw TSV.
        anchor = edit_start - 1
        anchor_index = anchor - first
        if 0 <= anchor_index < len(frame):
            last_inserted_index = edit_start + alt_edit_length - first
            if last_inserted_index <= len(raw_alt):
                segment = raw_alt[anchor_index:last_inserted_index]
                aligned[anchor_index] = np.max(segment) if np.isfinite(segment).all() else np.nan
                statuses[anchor_index] = "insertion_anchor_max"
            else:
                aligned[anchor_index] = np.nan
                statuses[anchor_index] = "unavailable_boundary"
            mapping[anchor_index] = np.nan
    elif ref_edit_length > 0 and alt_edit_length == 0:
        deleted = (positions >= edit_start) & (positions < edit_end)
        aligned[deleted] = 0.0
        statuses[deleted] = "deleted_reference_base"
        mapping[deleted] = np.nan
    elif delta and ref_edit_length and alt_edit_length:
        # No unique base correspondence exists inside a length-changing
        # replacement. Do not invent one; shared flanks still project exactly.
        replaced = (positions >= edit_start) & (positions < edit_end)
        aligned[replaced] = np.nan
        statuses[replaced] = "replacement_unmapped"
        mapping[replaced] = np.nan

    output = frame.copy()
    output["alt_prediction"] = aligned
    output["alt_sequence_index"] = mapping
    output["alignment_status"] = statuses
    metadata = {
        "version": TRACK_ALIGNMENT_VERSION,
        "method": "reference_coordinate_projection",
        "coordinate_basis": "GRCh38_reference_0_based",
        "variant": variant,
        "net_length_change": delta,
        "common_prefix_bases": prefix,
        "common_suffix_bases": suffix,
        "reference_edit_length": ref_edit_length,
        "alternate_edit_length": alt_edit_length,
        "insertion_policy": "maximum_of_shared_left_anchor_and_inserted_segment",
        "deletion_policy": "zero_at_deleted_reference_positions",
        "length_changing_replacement_policy": "NaN_within_unmapped_replacement",
        "unavailable_boundary_policy": "NaN",
        "unavailable_boundary_positions": int(np.sum(statuses == "unavailable_boundary")),
        "deleted_reference_positions": int(np.sum(statuses == "deleted_reference_base")),
        "raw_artifact": RAW_PREDICTION_NAME,
        "is_inference": False,
    }
    return output, metadata


def align_existing_prediction(results_dir: Path | str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Idempotently upgrade a saved raw prediction, preserving inference dates.

    Returns the whole status object. A previously aligned artifact is accepted
    only if both recorded hashes and the allele representation still match.
    """
    results_dir = Path(results_dir)
    prediction = results_dir / "frontal_cortex_prediction.tsv"
    raw = results_dir / RAW_PREDICTION_NAME
    status_path = results_dir / "frontal_cortex_prediction_status.json"
    if not prediction.is_file() or not status_path.is_file():
        raise ValueError("Prediction TSV and original inference status are required for alignment")
    status = json.loads(status_path.read_text())
    previous = status.get("visualization_alignment") or {}
    if previous.get("version") == TRACK_ALIGNMENT_VERSION:
        if not raw.is_file():
            raise ValueError("Aligned prediction is missing its original raw artifact")
        if previous.get("variant") != _variant(payload):
            raise ValueError("Aligned prediction belongs to different variant alleles")
        if previous.get("raw_sha256") != _sha256(raw) or previous.get("aligned_sha256") != _sha256(prediction):
            raise ValueError("Aligned prediction or preserved raw artifact has changed since alignment")
        return status
    if previous:
        raise ValueError("Unrecognized existing visualization alignment; do not apply alignment twice")
    if not raw.exists():
        shutil.copy2(prediction, raw)
    frame = pd.read_csv(raw, sep="\t", low_memory=False)
    if "alignment_status" in frame.columns:
        raise ValueError("Raw artifact already contains alignment markers; refusing double alignment")
    aligned, metadata = align_prediction_frame(frame, payload)
    temporary = prediction.with_name(prediction.name + f".alignment.tmp.{os.getpid()}")
    aligned.to_csv(temporary, sep="\t", index=False)
    temporary.replace(prediction)
    metadata.update(
        aligned_at=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        raw_sha256=_sha256(raw), aligned_sha256=_sha256(prediction),
    )
    status["visualization_alignment"] = metadata
    # Keep all original inference provenance/timestamps and cache receipt data.
    temp_status = status_path.with_name(status_path.name + f".alignment.tmp.{os.getpid()}")
    temp_status.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n")
    temp_status.replace(status_path)
    return status
