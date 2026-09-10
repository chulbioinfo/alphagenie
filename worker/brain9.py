"""Versioned, metadata-only manuscript grouping for fresh v0.20 score rows.

No API requests or saved numerical scores are used by this adapter. New or
changed catalogs require a reviewed new mapping version, never a Brain6 fallback.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

VERSION = "brain9_adult8_embryo_v1_20260909"
SCOPE = "brain9_adult8_embryo"
ANALYSIS_MODE = "custom_api_local_brain9"
ENDPOINT = "Brain9 (adult 8 + Embryo); non-brain tissues and cells display-only"
ROOT = Path(__file__).resolve().parents[1] / "data/manuscript_v020_20260909"
ASSET_HASHES = {
    "groups.json": "67d9fdf15f367b29404543e4407033c708de06d0081cf0f83529b467e4e07213",
    "tissue_payload.json": "c56fe57bc660ebb989365ede0872a5aff1430584a94bb4f1539c80e9f943a936",
}
FULL_GROUP_ORDER = [
    ("Cerebral cortex", "Cortex"),
    ("Hippocampal formation", "Hippocampal f."),
    ("Basal ganglia / striatum", "BG / striatum"),
    ("Amygdala", "Amygdala"),
    ("Diencephalic regions", "Diencephalon"),
    ("Midbrain", "Midbrain"),
    ("Cerebellum", "Cerebellum"),
    ("Whole brain", "Whole brain"),
    ("Embryo", "Embryo"),
    ("Non-brain tissues", "Non-brain tissues"),
    ("Cells & cell lines", "Cells / lines"),
]
BRAIN_TISSUE_GROUPS = tuple(group for group, _ in FULL_GROUP_ORDER[:9])
NONBRAIN_TISSUE_GROUPS = ("Non-brain tissues",)
CELL_AND_CELL_LINE_GROUPS = ("Cells & cell lines",)
DISPLAY_ONLY_GROUPS = (*NONBRAIN_TISSUE_GROUPS, *CELL_AND_CELL_LINE_GROUPS)
# Kept as an empty compatibility alias: neural models are within the cells pool,
# not a separate primary/developmental brain group.
SUPPORTIVE_NEURAL_GROUPS = ()
PLOT_SECTION_BOUNDARIES = (7.5, 8.5, 9.5)
PLOT_SECTION_LABELS = (
    {"label": "Adult brain tissues", "start": 0, "end": 7},
    {"label": "Embryo", "start": 8, "end": 8},
    {"label": "Non-brain tissues", "start": 9, "end": 9},
    {"label": "Cells / lines", "start": 10, "end": 10},
)
KEY_FIELDS = ("track_name", "biosample_name", "ontology_curie", "data_source")
CLASS_FIELDS = (*KEY_FIELDS, "biosample_type", "biosample_life_stage", "gtex_tissue")


def provenance() -> dict:
    return {"version": VERSION, "scope": SCOPE, "metadata_asset_sha256": ASSET_HASHES,
            "catalog_policy": "exact manuscript membership and classification metadata; fail on drift",
            "duplicate_rule": "median per real track / per (null_id, track_key), before null centering"}


@lru_cache(maxsize=1)
def registry() -> dict[str, dict]:
    assets = {}
    for name, digest in ASSET_HASHES.items():
        content = (ROOT / name).read_bytes()
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError("Brain9 classification asset integrity failure: " + name)
        assets[name] = json.loads(content)
    groups = assets["groups.json"]
    if [g["label"] for g in groups] != [g for g, _ in FULL_GROUP_ORDER]:
        raise ValueError("Brain9 group order mismatch")
    audit = {r["track_key"]: r for r in assets["tissue_payload.json"]["track_audit"]}
    result = {}
    for group in groups:
        for key in group["track_keys"]:
            if key in result or key not in audit:
                raise ValueError("Duplicate or missing Brain9 membership")
            raw = audit[key]
            result[key] = {field: str(raw.get("raw_" + field) or "") for field in CLASS_FIELDS}
            result[key].update(display_group=group["label"], analysis_group_id=group["id"],
                               included_in_brain9=group["included_in_brain9"], group_stage=group["stage"],
                               track_scope="brain9_primary" if group["included_in_brain9"] else "display_only",
                               mapping_rule_id=raw["mapping_rule_id"])
    if len(result) != 371 or set(result) != set(audit):
        raise ValueError("Incomplete manuscript classification catalog")
    return result


def canonicalize_scores(real: pd.DataFrame, null: pd.DataFrame, *, requested_null_depth: int | None,
                        audit_out: Path, expected_null_ids: list[str] | None = None):
    """Validate fixed track membership and return canonical, null-centered rows.

    Strict for every requested depth: missing tracks/null IDs, metadata drift and
    nonfinite raw scores fail. No imputation, subset fallback or silent drop.
    """
    catalog = registry()
    audit_out.parent.mkdir(parents=True, exist_ok=True)
    receipt = {**provenance(), "status": "checking", "expected_track_count": len(catalog)}

    def persist():
        audit_out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")

    def fail(message):
        receipt.update(status="failed", reason=message)
        persist()
        raise ValueError("Brain9 validation: " + message)

    frames, audit_rows = [], []
    for kind, original in (("real", real), ("null", null)):
        required = set(CLASS_FIELDS) | {"raw_score"} | ({"null_id"} if kind == "null" else set())
        if not required.issubset(original.columns):
            fail(kind + " scores lack required columns: " + ", ".join(sorted(required - set(original.columns))))
        frame = original.copy()
        for field in CLASS_FIELDS:
            frame[field] = frame[field].fillna("").astype(str)
        frame["track_key"] = frame[list(KEY_FIELDS)].agg("||".join, axis=1)
        metadata = frame[["track_key", *CLASS_FIELDS]].drop_duplicates()
        problems = []
        for record in metadata.to_dict("records"):
            known = catalog.get(record["track_key"])
            differences = [f for f in CLASS_FIELDS if known is not None and record[f] != known[f]]
            status = "unknown_track" if known is None else "metadata_drift" if differences else "matched"
            row = {**record, "source": kind, "classification_status": status,
                   "changed_fields": ",".join(differences), "classification_version": VERSION}
            if known is not None:
                row.update({f: known[f] for f in ("display_group", "analysis_group_id", "included_in_brain9",
                                                "group_stage", "track_scope", "mapping_rule_id")})
            audit_rows.append(row)
            if status != "matched":
                problems.append(status)
        pd.DataFrame(audit_rows).to_csv(audit_out.with_suffix(".tsv"), sep="\t", index=False)
        seen = set(frame["track_key"])
        receipt[kind] = {"raw_rows": len(frame), "observed_track_count": len(seen),
                         "missing_track_keys": sorted(set(catalog) - seen), "classification_errors": len(problems)}
        if problems:
            fail(kind + " catalog is unknown or classification metadata changed; review classification_audit.tsv")
        if seen != set(catalog):
            fail(kind + " track membership differs from the complete manuscript catalog")
        frame["raw_score"] = pd.to_numeric(frame["raw_score"], errors="coerce")
        if not np.isfinite(frame["raw_score"].to_numpy(dtype=float)).all():
            fail(kind + " contains nonfinite raw scores")
        if kind == "null":
            if frame["null_id"].isna().any() or frame["null_id"].astype(str).str.strip().eq("").any():
                fail("missing null ID")
            frame["null_id"] = frame["null_id"].astype(str)
        for field in ("display_group", "analysis_group_id", "included_in_brain9", "group_stage", "track_scope"):
            frame[field] = frame["track_key"].map({k: v[field] for k, v in catalog.items()})
        frame["classification_version"] = VERSION
        frames.append(frame)

    real, null = frames
    counts = null.groupby("null_id")["track_key"].nunique()
    receipt["observed_null_count"] = len(counts)
    receipt["requested_null_depth"] = requested_null_depth
    receipt["incomplete_null_ids"] = counts[counts != len(catalog)].index.tolist()
    if receipt["incomplete_null_ids"]:
        fail("every null must contain the same complete track set as the real variant")
    if requested_null_depth is not None and len(counts) != requested_null_depth:
        fail(f"requires {requested_null_depth} complete nulls; observed {len(counts)}")
    if expected_null_ids is not None:
        if len(set(expected_null_ids)) != len(expected_null_ids) or set(counts.index) != set(expected_null_ids):
            fail("scored null IDs differ from the sampled matched-null design")
    receipt["matched_null_design_ids_checked"] = expected_null_ids is not None
    real_group = real.groupby("track_key", sort=False)
    metadata = real_group.first().drop(columns="raw_score")
    metadata["raw_score"] = real_group["raw_score"].median()
    metadata["n_raw_effect_rows"] = real_group.size()
    metadata["n_duplicate_effect_rows"] = metadata["n_raw_effect_rows"] - 1
    real = metadata.reset_index()
    null = null.groupby(["null_id", "track_key"], sort=False, as_index=False)["raw_score"].median()
    centers = null.groupby("track_key")["raw_score"].median()
    for frame in (real, null):
        frame["null_median"] = frame["track_key"].map(centers)
        frame["effect"] = frame["raw_score"] - frame["null_median"]
    for field in ("display_group", "track_scope"):
        null[field] = null["track_key"].map({k: v[field] for k, v in catalog.items()})
    receipt.update(status="passed", group_track_counts=real.groupby("display_group").size().to_dict())
    persist()
    return real, null, receipt
