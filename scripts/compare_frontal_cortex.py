#!/usr/bin/env python3
"""Compare local fresh Frontal cortex artifacts with a sealed manuscript package.

Run with explicit --fresh-root, --sealed-root, and --output paths. This offline
tool imports no provider client, discovers no credentials, and records no input
directory paths in its report. A failed comparison exits with status 1.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    from .cross_validation_checks import SERIALIZATION_ABSOLUTE_TOLERANCE, numeric_comparison
except ImportError:
    from cross_validation_checks import SERIALIZATION_ABSOLUTE_TOLERANCE, numeric_comparison

COLUMNS = ("position", "ref_prediction", "alt_prediction")
TRACK_FIELDS = (
    "name", "strand", "Assay title", "ontology_curie", "biosample_name",
    "biosample_type", "biosample_life_stage", "gtex_tissue", "data_source",
    "endedness", "genetically_modified",
)


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def selected_status(status: dict) -> dict:
    metadata = status["track_metadata"]
    identity = {field: metadata.get(field) for field in TRACK_FIELDS}
    required = {"ontology_curie": "UBERON:0001870", "strand": ".", "gtex_tissue": "Brain_Cortex",
                "biosample_type": "tissue", "biosample_life_stage": "adult", "data_source": "gtex",
                "Assay title": "polyA plus RNA-seq"}
    if any(identity[field] != value for field, value in required.items()):
        raise ValueError("The curve is not the required adult GTEx Frontal cortex track")
    modified = identity["genetically_modified"]
    if isinstance(modified, str):
        if modified.strip().lower() not in {"true", "false"}:
            raise ValueError("Unrecognized genetically_modified track metadata")
        identity["genetically_modified"] = modified.strip().lower() == "true"
    provenance = status.get("inference_provenance", {})
    return {
        "interval": status["interval"], "ontology_terms": status["ontology_terms"],
        "track_idx": status["track_idx"], "track_identity": identity,
        **{key: provenance.get(key) for key in ("alphagenome_client_version", "requested_model_version",
                                               "resolved_model_version", "backend_revision_source")},
    }


def compare_values(old: dict, fresh: pd.DataFrame, kind: str, *, serialized: bool) -> dict:
    return {
        column: numeric_comparison(
            old[column], fresh[column].to_numpy(),
            atol=SERIALIZATION_ABSOLUTE_TOLERANCE if serialized and column != "position" else 0.0,
            allow_matching_nan=(kind == "aligned" and column == "alt_prediction"),
        )
        for column in COLUMNS
    }


def compare_context(fresh_root: Path, sealed_root: Path, name: str) -> dict[str, Any]:
    figure = {"rbfox1_16kb": "Figure2_RBFOX1_16kb", "ptchd1_1mb": "Figure4_PTCHD1_1Mb"}[name]
    fresh_dir = fresh_root / "contexts" / name / "results"
    old_dir = sealed_root / figure / "data/curves/raw_and_aligned"
    result = {}
    old_status_path = old_dir / ("prediction_status.json" if name == "ptchd1_1mb" else "frontal_cortex_prediction_status.json")
    old_status = json.loads(old_status_path.read_text(encoding="utf-8"))
    fresh_status_path = fresh_dir / "frontal_cortex_prediction_status.json"
    fresh_status = json.loads(fresh_status_path.read_text(encoding="utf-8"))
    if old_status.get("status") != "ok" or fresh_status.get("status") != "ok":
        raise ValueError("A supplied curve status does not record a successful prediction")
    for kind in ("raw", "aligned"):
        filename = "frontal_cortex_prediction_raw.tsv" if kind == "raw" else "frontal_cortex_prediction.tsv"
        fresh_path = fresh_dir / filename
        fresh = pd.read_csv(fresh_path, sep="\t", usecols=list(COLUMNS), float_precision="round_trip")
        if name == "rbfox1_16kb":
            old_path = old_dir / filename
            old = pd.read_csv(old_path, sep="\t", usecols=list(COLUMNS), float_precision="round_trip")
            old_arrays = {column: old[column].to_numpy() for column in COLUMNS}
        else:
            old_path = old_dir / ("returned_rna_predictions.npz" if kind == "raw" else "selected_aligned_prediction.npz")
            with np.load(old_path, allow_pickle=False) as arrays:
                if kind == "raw":
                    index = int(old_status["track_idx"])
                    old_arrays = {
                        "position": np.arange(int(arrays["interval_start"]), int(arrays["interval_end"]), dtype=np.int64),
                        "ref_prediction": arrays["reference"][:, index],
                        "alt_prediction": arrays["alternate"][:, index],
                    }
                else:
                    old_arrays = {"position": arrays["position"], "ref_prediction": arrays["reference"],
                                  "alt_prediction": arrays["alternate"]}
        result[kind] = compare_values(old_arrays, fresh, kind, serialized=name == "ptchd1_1mb")
        result[kind].update(fresh_sha256=sha256(fresh_path), sealed_sha256=sha256(old_path))
    old_selected, fresh_selected = selected_status(old_status), selected_status(fresh_status)
    result["selection"] = {
        "sealed": old_selected, "fresh": fresh_selected,
        "interval_exact": old_selected["interval"] == fresh_selected["interval"],
        "ontology_exact": old_selected["ontology_terms"] == fresh_selected["ontology_terms"],
        "track_identity_exact": old_selected["track_identity"] == fresh_selected["track_identity"],
        "fresh_status_sha256": sha256(fresh_status_path), "sealed_status_sha256": sha256(old_status_path),
    }
    result["all_numeric_exact"] = all(result[k][c]["exact"] for k in ("raw", "aligned") for c in COLUMNS)
    result["all_numeric_equivalent"] = all(result[k][c]["equivalent_at_serialization_tolerance"] for k in ("raw", "aligned") for c in COLUMNS)
    result["selection_exact"] = all(result["selection"][k] for k in ("interval_exact", "ontology_exact", "track_identity_exact"))
    return result


def build_report(fresh_root: Path, sealed_root: Path) -> dict:
    contexts = {name: compare_context(fresh_root, sealed_root, name) for name in ("rbfox1_16kb", "ptchd1_1mb")}
    return {
        "schema": "alphagenie_fresh_curve_cross_validation_v2",
        "status": "passed" if all(r["all_numeric_equivalent"] and r["selection_exact"] for r in contexts.values()) else "failed",
        "provider_calls": 0, "offline": True,
        "comparison": "explicit fresh Frontal cortex outputs versus sealed manuscript curve artifacts",
        "contexts": contexts,
        "interpretation": "This is an offline comparison of supplied outputs, not a second provider run or proof of the hidden backend checkpoint. Coordinates require exact equality. Binary-to-TSV prediction comparisons use at most 1e-15 absolute tolerance and zero relative tolerance; exact equality is reported separately.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fresh-root", required=True, type=Path, help="Run directory containing contexts/<context>/results")
    parser.add_argument("--sealed-root", required=True, type=Path, help="Extracted manuscript package containing Figure2 and Figure4 directories")
    parser.add_argument("--output", required=True, type=Path, help="New JSON report path; an existing file is never overwritten")
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("The output report already exists; choose a new report path")
    try:
        report = build_report(args.fresh_root, args.sealed_root)
    except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        # Do not print arbitrary exception text, which can contain input paths.
        report = {"schema": "alphagenie_fresh_curve_cross_validation_v2", "status": "failed",
                  "provider_calls": 0, "offline": True, "error_type": type(exc).__name__,
                  "reason": "Required artifacts are missing, unreadable, or have an unsupported schema"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": report["status"], "provider_calls": 0}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
