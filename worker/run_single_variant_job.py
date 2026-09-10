from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import textwrap
from typing import Any, Callable
import uuid

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams.update({"svg.fonttype": "none", "pdf.fonttype": 42, "ps.fonttype": 42})
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.job_store import update_job
from alphagenie.security import redact
from worker.rna_curve import (
    SPEC_ID as CURVE_SPEC_ID, TRACK_SPEC as CURVE_TRACK_SPEC,
    ONTOLOGY as CURVE_ONTOLOGY, choose_frontal_cortex_track,
    selection_receipt, selection_matches, track_pair_to_frame,
)
from worker.inference_provenance import (
    cache_provenance_matches,
    complete_inference,
    force_prediction_refresh,
    inference_identity,
    load_score_provenance,
    model_create_kwargs,
    start_inference,
    utc_now,
    figure_provenance_label,
)


PTCHD1_ALT = "TCGCCGCCGCCGCGGGCGCCGCTGCCGC"
PREDICTION_TRACK_ALIGNMENT_VERSION = 1

DEMO_SPECS: dict[str, dict[str, Any]] = {
    "PTCHD1_ins27": {
        "variant_group_id": "PTCHD1_ins27",
        "gene_symbol": "PTCHD1",
        "chrom": "chrX",
        "pos1": 23334765,
        "ref": "T",
        "alt": PTCHD1_ALT,
        "sequence_length": 1_048_576,
        "track_prefix": "PTCHD1",
        "demo_cache_dir": APP_ROOT / "data" / "demo" / "PTCHD1_ins27_v016",
    },
    "RBFOX1_del3": {
        "variant_group_id": "RBFOX1_del3",
        "gene_symbol": "RBFOX1",
        "chrom": "chr16",
        "pos1": 6018925,
        "ref": "TCCG",
        "alt": "T",
        "sequence_length": 16_384,
        "track_prefix": "RBFOX1",
        "demo_cache_dir": APP_ROOT / "data" / "demo" / "RBFOX1_del3_seq16384_v016",
    },
}

from worker.brain9 import (
    BRAIN_TISSUE_GROUPS, NONBRAIN_TISSUE_GROUPS, SUPPORTIVE_NEURAL_GROUPS,
    CELL_AND_CELL_LINE_GROUPS, FULL_GROUP_ORDER, PLOT_SECTION_BOUNDARIES, PLOT_SECTION_LABELS,
    DISPLAY_ONLY_GROUPS, SCOPE as BRAIN9_SCOPE, provenance as classification_provenance,
    canonicalize_scores,
)

PRIMARY_BRAIN_TISSUE_GROUPS = set(BRAIN_TISSUE_GROUPS)
BRAIN_GROUPS = PRIMARY_BRAIN_TISSUE_GROUPS


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(redact(payload), indent=2, sort_keys=True) + "\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(redact(text))


def sha256_file(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def prediction_alignment_valid(status: dict[str, Any], prediction: Path, raw: Path) -> bool:
    alignment = status.get("visualization_alignment") or {}
    return (
        alignment.get("version") == PREDICTION_TRACK_ALIGNMENT_VERSION
        and prediction.is_file() and raw.is_file()
        and alignment.get("raw_sha256") == sha256_file(raw)
        and alignment.get("aligned_sha256") == sha256_file(prediction)
    )


def safe_json_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def first_safe_json_float(row: Any, *names: str) -> float | None:
    for name in names:
        value = getattr(row, name, None)
        out = safe_json_float(value)
        if out is not None:
            return out
    return None


def make_variant_tsv(path: Path, payload: dict[str, Any]) -> None:
    cols = [
        "variant_group_id",
        "gene_symbol",
        "variant_class",
        "representation",
        "sub_index",
        "chrom",
        "pos1",
        "ref",
        "alt",
    ]
    row = {
        "variant_group_id": payload["variant_group_id"],
        "gene_symbol": payload["gene_symbol"],
        "variant_class": payload.get("variant_class") or infer_variant_class(payload["ref"], payload["alt"]),
        "representation": "input",
        "sub_index": "0",
        "chrom": payload["chrom"],
        "pos1": str(payload["pos1"]),
        "ref": payload["ref"].upper(),
        "alt": payload["alt"].upper(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([row], columns=cols).to_csv(path, sep="\t", index=False)


def infer_variant_class(ref: str, alt: str) -> str:
    ref = str(ref).upper()
    alt = str(alt).upper()
    if len(ref) == len(alt) == 1:
        return "substitution_1snv"
    if len(ref) == len(alt):
        return f"substitution_{len(ref)}bp"
    if len(ref) > len(alt):
        return f"deletion_{len(ref) - len(alt)}bp"
    return f"insertion_{len(alt) - len(ref)}bp"


def demo_spec_for_payload(payload: dict[str, Any]) -> dict[str, Any]:
    variant_group_id = str(payload.get("variant_group_id", ""))
    spec = DEMO_SPECS.get(variant_group_id)
    if spec is None:
        allowed = ", ".join(sorted(DEMO_SPECS))
        raise ValueError(f"demo_cached accepts only publication-quality cached demo variants: {allowed}")
    configured_manifest = os.environ.get("AG_WEB_RELEASE_MANIFEST", "").strip()
    manifest_path = Path(configured_manifest) if configured_manifest else APP_ROOT / "data" / "releases" / "current.json"
    if not manifest_path.exists():
        if configured_manifest:
            raise FileNotFoundError(f"Configured publication release manifest is missing: {manifest_path}")
        return dict(spec)
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("validation", {}).get("passed") is not True:
        raise ValueError("Selected publication release has not passed validation")
    preset_id = {"PTCHD1_ins27": "ptchd1", "RBFOX1_del3": "rbfox1"}[variant_group_id]
    cache_dir = Path(manifest["single_variant_results"][preset_id])
    if not cache_dir.is_absolute() or not cache_dir.is_dir():
        raise ValueError(f"Selected publication release has an invalid {preset_id} results directory")
    config = json.loads((cache_dir.parent / "input" / "run_config.json").read_text())
    config = config.get("payload", config)
    required = ("variant_group_id", "gene_symbol", "chrom", "pos1", "ref", "alt", "sequence_length")
    if any(key not in config for key in required) or config["variant_group_id"] != variant_group_id:
        raise ValueError(f"Selected publication release has incomplete or mismatched {preset_id} inputs")
    return {
        **spec,
        **{key: config[key] for key in required},
        "demo_cache_dir": cache_dir,
        "publication_release_id": manifest["release_id"],
    }


def validate_demo_payload(payload: dict[str, Any]) -> dict[str, Any]:
    expected = demo_spec_for_payload(payload)
    mismatches = []
    for key, value in expected.items():
        if key in {"track_prefix", "demo_cache_dir", "publication_release_id"}:
            continue
        observed = payload.get(key)
        if key in {"pos1", "sequence_length"}:
            observed = int(observed)
        if str(observed).upper() != str(value).upper():
            mismatches.append(f"{key}: observed={observed!r}, expected={value!r}")
    if mismatches:
        raise ValueError(
            f"demo_cached preset mismatch for {expected['variant_group_id']}. "
            + "; ".join(mismatches)
        )
    return expected


def load_demo_outputs(payload: dict[str, Any], v04_reference_run: Path, out_dir: Path) -> dict[str, Any]:
    spec = validate_demo_payload(payload)
    cache_dir = spec.get("demo_cache_dir")
    if cache_dir:
        cache_dir = Path(cache_dir)
        table_src = cache_dir / "source_table.tsv"
        group_src = cache_dir / "group_summary.tsv"
        summary_src = cache_dir / "consensus_summary.json"
        missing = [str(p) for p in [table_src, group_src, summary_src] if not p.exists()]
        if missing:
            raise FileNotFoundError("missing cached demo source files: " + ", ".join(missing))
        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(table_src, out_dir / "source_table.tsv")
        shutil.copy2(group_src, out_dir / "group_summary.tsv")
        compact_exports = {}
        missing_compact_exports = []
        for name in ("null_consensus.tsv", "null_group_medians.tsv", "matched_null_design.tsv"):
            compact_source = cache_dir / name
            if compact_source.is_file():
                shutil.copy2(compact_source, out_dir / name)
                compact_exports[Path(name).stem] = name
            else:
                missing_compact_exports.append(name)
                previous = out_dir / name
                if previous.exists():
                    previous.rename(previous.with_name(f"{previous.name}.previous-{uuid.uuid4().hex}"))
        summary = json.loads(summary_src.read_text())
        summary["reproducibility_source_files"] = compact_exports
        summary["unavailable_reproducibility_source_files"] = missing_compact_exports
        summary["matched_null_design_available"] = "matched_null_design" in compact_exports
        summary["run_mode"] = "demo_cached"
        summary["api_called"] = False
        if spec.get("publication_release_id"):
            summary["publication_release_id"] = spec["publication_release_id"]
            summary["demo_source"] = f"Frozen validated publication release {spec['publication_release_id']}"
            summary["publication_release_results_dir"] = str(cache_dir)
        else:
            summary["source_v04_reference_run"] = str(v04_reference_run)
            summary["demo_source"] = (
                "v0.16 brain_tissue_6_groups summary generated from v0.4 PER_GROUP=1000 "
                "production source tables when matching null distributions are available"
            )
        write_json(out_dir / "consensus_summary.json", summary)
        return summary

    track_prefix = str(spec["track_prefix"])
    variant_group_id = str(spec["variant_group_id"])
    source_dir = v04_reference_run / "results" / "variant_figure_updates"
    table_src = source_dir / f"{track_prefix}_track_level_effects.tsv"
    group_src = source_dir / f"{track_prefix}_group_summary.tsv"
    consensus_src = v04_reference_run / "results" / "tables" / "CANDIDATE13_consensus_fixed_interval_tests.tsv"
    missing = [str(p) for p in [table_src, group_src, consensus_src] if not p.exists()]
    if missing:
        raise FileNotFoundError("missing v0.4 demo source files: " + ", ".join(missing))

    out_dir.mkdir(parents=True, exist_ok=True)
    table_out = out_dir / "source_table.tsv"
    group_out = out_dir / "group_summary.tsv"
    shutil.copy2(table_src, table_out)
    shutil.copy2(group_src, group_out)

    consensus = pd.read_csv(consensus_src, sep="\t")
    row = consensus[consensus["variant_group_id"].astype(str).eq(variant_group_id)]
    if row.empty:
        raise ValueError(f"{variant_group_id} row not found in CANDIDATE13 consensus table")
    summary = row.iloc[0].to_dict()
    summary["run_mode"] = "demo_cached"
    summary["api_called"] = False
    summary["source_v04_reference_run"] = str(v04_reference_run)
    summary["demo_source"] = "v0.4 PER_GROUP=1000 publication-quality cached result"
    write_json(out_dir / "consensus_summary.json", summary)
    return summary


def load_demo_prediction(payload: dict[str, Any], results_dir: Path) -> dict[str, Any]:
    """Load the track bundled with a frozen demo; never mix in live inference."""
    spec = validate_demo_payload(payload)
    cache_dir = Path(spec["demo_cache_dir"])
    status_path = cache_dir / "whole_brain_prediction_status.json"
    artifacts = [cache_dir / name for name in ("whole_brain_prediction.tsv", "whole_brain_prediction_raw.tsv", "gene_model.tsv")]
    status: dict[str, Any] = {
        "status": "unavailable",
        "reason": "Frozen demo does not include a versioned whole-brain prediction track.",
        "api_called_this_request": False,
        "cache": "frozen_demo_missing",
    }
    if status_path.is_file() and all(path.is_file() and path.stat().st_size > 0 for path in artifacts):
        recorded = json.loads(status_path.read_text())
        provenance = recorded.get("inference_provenance") or {}
        if (
            recorded.get("status") == "ok"
            and provenance.get("inference_backend_revision")
            and provenance.get("inference_started_at")
            and provenance.get("inference_completed_at")
            and prediction_alignment_valid(recorded, artifacts[0], artifacts[1])
        ):
            for artifact in artifacts:
                shutil.copy2(artifact, results_dir / artifact.name)
            status = {**recorded, "cache": "frozen_demo", "cache_loaded_at": utc_now(), "api_called_this_request": False}
    if status["status"] != "ok":
        for artifact in artifacts:
            previous = results_dir / artifact.name
            if previous.exists():
                previous.rename(previous.with_name(f"{previous.name}.previous-{uuid.uuid4().hex}"))
    write_json(results_dir / "whole_brain_prediction_status.json", status)
    return status


def prediction_cache_key(
    payload: dict[str, Any],
    *,
    gencode_gtf: Path | None = None,
    identity: dict[str, Any] | None = None,
) -> str:
    core = json.dumps(
        {
            "variant_group_id": str(payload.get("variant_group_id", "")),
            "gene_symbol": str(payload.get("gene_symbol", "")),
            "target_gene": str(payload.get("target_gene") or payload.get("gene_symbol", "")),
            "chrom": str(payload.get("chrom", "")),
            "pos1": int(payload.get("pos1", 0)),
            "ref": str(payload.get("ref", "")).upper(),
            "alt": str(payload.get("alt", "")).upper(),
            "sequence_length": int(payload.get("sequence_length", 1_048_576)),
            "inference_identity": identity or inference_identity(payload, gencode_gtf),
            "output_type": "RNA_SEQ",
            "ontology_terms": [CURVE_ONTOLOGY],
            "track_selection_version": 2,
            "curve_spec_id": CURVE_SPEC_ID,
            "required_track_metadata": CURVE_TRACK_SPEC,
            "track_alignment_version": PREDICTION_TRACK_ALIGNMENT_VERSION,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(core.encode("utf-8")).hexdigest()[:16]
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(payload.get("variant_group_id", "variant"))).strip("_")
    return f"{safe_id}_{digest}"


def parse_gtf_attributes(attr_text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for field in attr_text.rstrip(";").split(";"):
        field = field.strip()
        if not field:
            continue
        parts = field.split(" ", 1)
        if len(parts) != 2:
            continue
        out[parts[0]] = parts[1].strip().strip('"')
    return out


def write_gene_model_tsv(
    *,
    gtf_path: Path,
    payload: dict[str, Any],
    interval_start: int,
    interval_end: int,
    out_path: Path,
) -> None:
    target_gene = str(payload.get("target_gene") or payload.get("gene_symbol", "")).upper()
    chrom = str(payload.get("chrom", ""))
    gene_rows: list[dict[str, Any]] = []
    transcript_rows: list[dict[str, Any]] = []
    exon_rows: list[dict[str, Any]] = []

    opener = gzip.open if str(gtf_path).endswith(".gz") else open
    with opener(gtf_path, "rt") as handle:
        for line in handle:
            if not line or line.startswith("#"):
                continue
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 9 or fields[0] != chrom:
                continue
            feature = fields[2]
            if feature not in {"gene", "transcript", "exon"}:
                continue
            attrs = parse_gtf_attributes(fields[8])
            if attrs.get("gene_name", "").upper() != target_gene:
                continue
            start0 = int(fields[3]) - 1
            end0 = int(fields[4])
            strand = fields[6]
            row = {
                "feature": feature,
                "chrom": fields[0],
                "start": start0,
                "end": end0,
                "strand": strand,
                "gene_name": attrs.get("gene_name", target_gene),
                "gene_id": attrs.get("gene_id", ""),
                "transcript_id": attrs.get("transcript_id", ""),
                "transcript_name": attrs.get("transcript_name", ""),
                "tag": attrs.get("tag", ""),
                "raw_attributes": fields[8],
            }
            if feature == "gene":
                gene_rows.append(row)
            elif feature == "transcript":
                transcript_rows.append(row)
            else:
                exon_rows.append(row)

    columns = [
        "feature",
        "chrom",
        "start",
        "end",
        "strand",
        "gene_name",
        "gene_id",
        "transcript_id",
        "transcript_name",
        "selected_transcript_id",
        "selected_transcript_name",
        "selection_rule",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not exon_rows and not gene_rows:
        pd.DataFrame(columns=columns).to_csv(out_path, sep="\t", index=False)
        return

    selected_tid = ""
    selected_name = ""
    selection_rule = "gene_extent_only"
    if exon_rows:
        exon_df = pd.DataFrame(exon_rows)
        transcript_df = pd.DataFrame(transcript_rows) if transcript_rows else pd.DataFrame()
        candidates = []
        for tid, sub in exon_df.groupby("transcript_id", dropna=False):
            tid = str(tid)
            total_exon = int((sub["end"] - sub["start"]).sum())
            span = int(sub["end"].max() - sub["start"].min())
            raw = ""
            name = ""
            if not transcript_df.empty:
                hit = transcript_df[transcript_df["transcript_id"].astype(str).eq(tid)]
                if not hit.empty:
                    raw = str(hit.iloc[0].get("raw_attributes", ""))
                    name = str(hit.iloc[0].get("transcript_name", ""))
            priority = 0
            if "MANE_Select" in raw:
                priority = 3
            elif "Ensembl_canonical" in raw:
                priority = 2
            elif "appris_principal" in raw:
                priority = 1
            candidates.append((priority, total_exon, span, tid, name))
        candidates.sort(reverse=True)
        _, _, _, selected_tid, selected_name = candidates[0]
        selection_rule = "MANE_Select/Ensembl_canonical/APPRIS priority, then exon length"
        exon_rows = [row for row in exon_rows if str(row.get("transcript_id", "")) == selected_tid]

    if gene_rows:
        gene = dict(gene_rows[0])
    else:
        starts = [int(row["start"]) for row in exon_rows]
        ends = [int(row["end"]) for row in exon_rows]
        strand = str(exon_rows[0].get("strand", ".")) if exon_rows else "."
        gene = {
            "feature": "gene",
            "chrom": chrom,
            "start": min(starts),
            "end": max(ends),
            "strand": strand,
            "gene_name": target_gene,
            "gene_id": "",
            "transcript_id": "",
            "transcript_name": "",
        }

    rows = [gene]
    rows.extend(
        row
        for row in exon_rows
        if int(row["end"]) >= interval_start and int(row["start"]) <= interval_end
    )
    for row in rows:
        row["selected_transcript_id"] = selected_tid
        row["selected_transcript_name"] = selected_name
        row["selection_rule"] = selection_rule
    pd.DataFrame(rows, columns=columns).to_csv(out_path, sep="\t", index=False)


def generate_frontal_cortex_prediction(
    *,
    payload: dict[str, Any],
    prediction_out: Path,
    gene_model_out: Path,
    status_out: Path,
    gencode_gtf: Path,
    identity: dict[str, Any] | None = None,
    cache_key: str | None = None,
) -> dict[str, Any]:
    identity = identity or inference_identity(payload, gencode_gtf)
    cache_key = cache_key or prediction_cache_key(payload, identity=identity)
    api_key = os.environ.get("ALPHA_GENOME_API_KEY", "").strip()
    if not api_key:
        status = {
            "status": "unavailable",
            "reason": "ALPHA_GENOME_API_KEY is not set; no synthetic REF/ALT prediction track was generated.",
            "prediction_cache_key": cache_key,
            "api_called": False,
        }
        write_json(status_out, status)
        return status

    from alphagenome.data import genome
    from alphagenome.models import dna_client
    from worker.prediction_alignment import align_prediction_frame

    variant = genome.Variant(
        chromosome=str(payload["chrom"]),
        position=int(payload["pos1"]),
        reference_bases=str(payload["ref"]).upper(),
        alternate_bases=str(payload["alt"]).upper(),
        name=str(payload.get("variant_group_id") or "variant"),
    )
    sequence_length = int(payload.get("sequence_length", 1_048_576))
    interval = variant.reference_interval.resize(sequence_length)
    model = dna_client.create(api_key, **model_create_kwargs(identity, dna_client))
    provenance = start_inference(identity, method="predict_variant.RNA_SEQ")
    try:
        out = model.predict_variant(
            interval=interval,
            variant=variant,
            requested_outputs={dna_client.OutputType.RNA_SEQ},
            organism=dna_client.Organism.HOMO_SAPIENS,
            ontology_terms=[CURVE_ONTOLOGY],
        )
    except Exception as exc:
        status = {
            "status": "failed",
            "reason": f"{type(exc).__name__}: {exc}",
            "api_called": True,
            "prediction_cache_key": cache_key,
            "inference_provenance": {**provenance, "inference_failed_at": utc_now()},
        }
        write_json(status_out, status)
        return status
    provenance = complete_inference(provenance)
    write_json(status_out, {
        "status": "processing",
        "api_called": True,
        "prediction_cache_key": cache_key,
        "inference_provenance": provenance,
    })
    ref_td = getattr(out.reference, "rna_seq", None)
    alt_td = getattr(out.alternate, "rna_seq", None)
    if ref_td is None or alt_td is None:
        status = {
            "status": "unavailable",
            "reason": "AlphaGenome returned no RNA_SEQ TrackData.",
            "api_called": True,
            "prediction_cache_key": cache_key,
            "inference_provenance": provenance,
        }
        write_json(status_out, status)
        return status

    metadata = ref_td.metadata.reset_index(drop=True).copy()
    alt_metadata = alt_td.metadata.reset_index(drop=True).copy()
    try:
        selection = selection_receipt(metadata, alt_metadata)
        track_idx = selection["reference_track_index"]
        alt_track_idx = selection["alternate_track_index"]
        prediction = track_pair_to_frame(ref_td, alt_td, track_idx, alt_track_idx)
        if (ref_td.interval.chromosome, ref_td.interval.start, ref_td.interval.end) != (interval.chromosome, interval.start, interval.end):
            raise ValueError("RNA output interval does not match the requested interval")
    except ValueError as exc:
        status = {"status": "unavailable", "reason": str(exc), "api_called": True,
                  "prediction_cache_key": cache_key, "inference_provenance": provenance,
                  "curve_spec_id": CURVE_SPEC_ID, "ontology_terms": [CURVE_ONTOLOGY]}
        write_json(status_out, status)
        return status
    meta_row = metadata.iloc[track_idx].to_dict()
    alt_meta_row = alt_metadata.iloc[alt_track_idx].to_dict()
    for key, value in meta_row.items():
        prediction[key] = value
    prediction["track_idx"] = track_idx
    prediction["alternate_track_idx"] = alt_track_idx
    prediction["curve_spec_id"] = CURVE_SPEC_ID
    prediction["variant_group_id"] = payload.get("variant_group_id")
    prediction["gene_symbol"] = payload.get("gene_symbol")
    prediction_out.parent.mkdir(parents=True, exist_ok=True)
    raw_prediction_out = prediction_out.with_name("frontal_cortex_prediction_raw.tsv")
    prediction.to_csv(raw_prediction_out, sep="\t", index=False)
    prediction, alignment_metadata = align_prediction_frame(prediction, payload)
    prediction.to_csv(prediction_out, sep="\t", index=False)
    write_gene_model_tsv(
        gtf_path=gencode_gtf,
        payload=payload,
        interval_start=int(interval.start),
        interval_end=int(interval.end),
        out_path=gene_model_out,
    )
    status = {
        "status": "ok",
        "source": "AlphaGenome predict_variant RNA_SEQ",
        "api_called": True,
        "prediction_cache_key": cache_key,
        "inference_provenance": provenance,
        "ontology_terms": [CURVE_ONTOLOGY],
        "interval": {"chrom": interval.chromosome, "start": int(interval.start), "end": int(interval.end)},
        "track_idx": track_idx,
        "track_metadata": {str(k): str(v) for k, v in meta_row.items()},
        "alternate_track_metadata": {str(k): str(v) for k, v in alt_meta_row.items()},
        "track_selection": selection,
        "curve_spec_id": CURVE_SPEC_ID,
        "tissue_label": "Frontal cortex",
        "resolution_bp": 1,
        "input_sequence_length": sequence_length,
        "visualization_alignment": {
            **alignment_metadata,
            "aligned_at": utc_now(),
            "raw_artifact": raw_prediction_out.name,
            "raw_sha256": sha256_file(raw_prediction_out),
            "aligned_sha256": sha256_file(prediction_out),
        },
    }
    write_json(status_out, status)
    return status


def ensure_frontal_cortex_prediction(
    *,
    payload: dict[str, Any],
    results_dir: Path,
    cache_root: Path,
    gencode_gtf: Path,
) -> dict[str, Any]:
    prediction_out = results_dir / "frontal_cortex_prediction.tsv"
    raw_prediction_out = results_dir / "frontal_cortex_prediction_raw.tsv"
    gene_model_out = results_dir / "gene_model.tsv"
    status_out = results_dir / "frontal_cortex_prediction_status.json"
    identity = inference_identity(payload, gencode_gtf)
    key = prediction_cache_key(payload, identity=identity)
    key_dir = cache_root / "_prediction_cache" / key
    pointer_path = key_dir / "current.json"
    force_refresh = force_prediction_refresh(payload)
    cache_miss_reason = "forced_refresh" if force_refresh else "missing_or_unversioned_cache"

    # Legacy flat cache entries are intentionally ignored. A successful, versioned
    # generation must have complete inference/alignment provenance and all artifacts.
    if not force_refresh and pointer_path.is_file():
        try:
            pointer = json.loads(pointer_path.read_text())
            cache_dir = (key_dir / pointer["generation"]).resolve()
            if not cache_dir.is_relative_to(key_dir.resolve()):
                raise ValueError("cache generation is outside its identity directory")
            cache_prediction = cache_dir / "frontal_cortex_prediction.tsv"
            cache_raw = cache_dir / "frontal_cortex_prediction_raw.tsv"
            cache_gene = cache_dir / "gene_model.tsv"
            cache_status = cache_dir / "frontal_cortex_prediction_status.json"
            status = json.loads(cache_status.read_text())
            artifacts = (cache_prediction, cache_raw, cache_gene, cache_status)
            if not all(path.is_file() and path.stat().st_size > 0 for path in artifacts):
                raise ValueError("cache generation is incomplete")
            if not selection_matches(status, payload):
                raise ValueError("cache does not contain the required Frontal cortex track identity")
            if not cache_provenance_matches(status, identity, key):
                raise ValueError("cache inference provenance is missing or incompatible")
            if not prediction_alignment_valid(status, cache_prediction, cache_raw):
                raise ValueError("cache coordinate alignment or artifact checksums are incompatible")
            results_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cache_prediction, prediction_out)
            shutil.copy2(cache_raw, raw_prediction_out)
            shutil.copy2(cache_gene, gene_model_out)
            status = {**status, "cache": "hit", "cache_loaded_at": utc_now(), "api_called_this_request": False}
            write_json(status_out, status)
            return status
        except (OSError, ValueError, KeyError, TypeError) as exc:
            cache_miss_reason = f"invalid_cache: {exc}"

    # Stage every attempt separately. A failed refresh must neither publish a
    # stale curve as a new result nor overwrite a previously valid generation.
    generation = f"generations/{uuid.uuid4().hex}"
    cache_dir = key_dir / generation
    cache_prediction = cache_dir / "frontal_cortex_prediction.tsv"
    cache_raw = cache_dir / "frontal_cortex_prediction_raw.tsv"
    cache_gene = cache_dir / "gene_model.tsv"
    cache_status = cache_dir / "frontal_cortex_prediction_status.json"

    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        status = generate_frontal_cortex_prediction(
            payload=payload,
            prediction_out=cache_prediction,
            gene_model_out=cache_gene,
            status_out=cache_status,
            gencode_gtf=gencode_gtf,
            identity=identity,
            cache_key=key,
        )
    except Exception as exc:  # noqa: BLE001
        recorded = json.loads(cache_status.read_text()) if cache_status.is_file() else {}
        status = {**recorded, "status": "failed", "reason": f"{type(exc).__name__}: {exc}", "prediction_cache_key": key}
        write_json(cache_status, status)

    results_dir.mkdir(parents=True, exist_ok=True)
    valid = selection_matches(status, payload) and cache_provenance_matches(status, identity, key) and all(
        path.is_file() and path.stat().st_size > 0 for path in (cache_prediction, cache_raw, cache_gene)
    ) and prediction_alignment_valid(status, cache_prediction, cache_raw)
    if valid:
        shutil.copy2(cache_prediction, prediction_out)
        shutil.copy2(cache_raw, raw_prediction_out)
        shutil.copy2(cache_gene, gene_model_out)
        pointer_temp = key_dir / f"current.{uuid.uuid4().hex}.tmp"
        write_json(pointer_temp, {"generation": generation, "prediction_cache_key": key})
        os.replace(pointer_temp, pointer_path)
    elif status.get("status") == "ok":
        status = {**status, "status": "failed", "reason": "Generated prediction artifacts or provenance are incomplete."}
    if not valid:
        # Preserve any previous per-job figures, but make them unavailable to
        # downstream plotting during this failed attempt.
        for artifact in (prediction_out, raw_prediction_out, gene_model_out):
            if artifact.exists():
                artifact.rename(artifact.with_name(f"{artifact.name}.previous-{uuid.uuid4().hex}"))
    status = dict(status)
    status["cache"] = "miss"
    status["cache_miss_reason"] = cache_miss_reason
    status["cache_generation"] = generation
    status["api_called_this_request"] = bool(status.get("api_called"))
    write_json(status_out, status)
    return status


def prediction_files_available(prediction_path: Path, gene_model_path: Path) -> bool:
    return prediction_path.exists() and gene_model_path.exists() and prediction_path.stat().st_size > 0


def plot_frontal_cortex_prediction_axes(
    ax_gene: Any,
    ax_pred: Any,
    ax_delta: Any,
    *,
    prediction_path: Path,
    gene_model_path: Path,
    payload_summary: dict[str, Any],
    font_scale: float = 1.0,
) -> bool:
    def fs(value: float) -> float:
        return max(1.0, float(value) * float(font_scale or 1.0))

    if not prediction_files_available(prediction_path, gene_model_path):
        ax_gene.axis("off")
        ax_pred.axis("off")
        ax_delta.axis("off")
        ax_pred.text(
            0.5,
            0.5,
            "Frontal cortex REF/ALT RNA prediction track unavailable",
            ha="center",
            va="center",
            transform=ax_pred.transAxes,
            fontsize=fs(9),
            color="#6b7280",
        )
        return False

    pred = pd.read_csv(prediction_path, sep="\t")
    gene = pd.read_csv(gene_model_path, sep="\t")
    if pred.empty or not {"position", "ref_prediction", "alt_prediction"}.issubset(pred.columns):
        ax_gene.axis("off")
        ax_pred.axis("off")
        ax_delta.axis("off")
        return False

    pred = pred.sort_values("position").copy()
    x_full = pred["position"].to_numpy(dtype=float) / 1e6
    ref_full = pd.to_numeric(pred["ref_prediction"], errors="coerce").to_numpy(dtype=float)
    alt_full = pd.to_numeric(pred["alt_prediction"], errors="coerce").to_numpy(dtype=float)
    finite = np.concatenate([ref_full[np.isfinite(ref_full)], alt_full[np.isfinite(alt_full)]])
    delta_full = alt_full - ref_full
    delta_finite = delta_full[np.isfinite(delta_full)]
    max_observed = float(np.nanmax(finite)) if finite.size else np.nan
    if finite.size:
        # A few high exonic prediction peaks can flatten promoter-proximal REF/ALT
        # differences. Use a robust display limit and record the clipping visually.
        robust_ymax = float(np.nanquantile(finite, 0.995)) * 1.2
        ymax = max(0.02, robust_ymax)
        if np.isfinite(max_observed):
            ymax = min(ymax, max_observed * 1.18)
    else:
        ymax = 1.0
    is_clipped = bool(np.isfinite(max_observed) and max_observed > ymax * 1.05)
    if delta_finite.size:
        delta_min = float(np.nanmin(delta_finite))
        delta_max = float(np.nanmax(delta_finite))
        delta_span = max(delta_max - delta_min, abs(delta_max), abs(delta_min), 1e-6)
        delta_pad = delta_span * 0.08
        delta_ymin = min(0.0, delta_min) - delta_pad
        delta_ymax = max(0.0, delta_max) + delta_pad
        delta_linthresh = max(float(np.nanquantile(np.abs(delta_finite), 0.99)), 1e-6)
    else:
        delta_min = np.nan
        delta_max = np.nan
        delta_ymin = -1.0
        delta_ymax = 1.0
        delta_linthresh = 1e-6
    max_points = 7000
    if len(pred) > max_points:
        pred = pred.iloc[:: int(np.ceil(len(pred) / max_points)), :].copy()
    x = pred["position"].to_numpy(dtype=float) / 1e6
    ref = pd.to_numeric(pred["ref_prediction"], errors="coerce").to_numpy(dtype=float)
    alt = pd.to_numeric(pred["alt_prediction"], errors="coerce").to_numpy(dtype=float)
    delta = alt - ref

    variant_pos = safe_json_float(payload_summary.get("pos1"))
    if variant_pos is None:
        variant_pos = safe_json_float(payload_summary.get("position"))
    variant_x = float(variant_pos) / 1e6 if variant_pos is not None else None

    plot_start = float(np.nanmin(x_full))
    plot_end = float(np.nanmax(x_full))
    if not gene.empty and {"start", "end"}.issubset(gene.columns):
        starts = pd.to_numeric(gene["start"], errors="coerce")
        ends = pd.to_numeric(gene["end"], errors="coerce")
        overlap = (starts <= plot_end * 1e6) & (ends >= plot_start * 1e6)
        if overlap.any():
            g_start = float(np.nanmin(starts[overlap])) / 1e6
            g_end = float(np.nanmax(ends[overlap])) / 1e6
            pad = max(0.01, (g_end - g_start) * 0.12)
            plot_start = max(float(np.nanmin(x_full)), g_start - pad)
            plot_end = min(float(np.nanmax(x_full)), g_end + pad)
    if variant_x is not None and (variant_x < plot_start or variant_x > plot_end):
        span = plot_end - plot_start
        plot_start = max(float(np.nanmin(x_full)), min(plot_start, variant_x - span * 0.2))
        plot_end = min(float(np.nanmax(x_full)), max(plot_end, variant_x + span * 0.2))

    ax_gene.set_xlim(plot_start, plot_end)
    ax_pred.set_xlim(plot_start, plot_end)
    ax_delta.set_xlim(plot_start, plot_end)
    ax_pred.fill_between(x, 0, ref, color="#5f6368", alpha=0.20, linewidth=0)
    ax_pred.plot(x, ref, color="#222222", linewidth=1.0, label="REF")
    ax_pred.plot(x, alt, color="#e729d8", linewidth=1.0, label="ALT")
    if variant_x is not None:
        ax_pred.axvline(variant_x, color="#e729d8", linewidth=0.8, alpha=0.85)
        ax_delta.axvline(variant_x, color="#e729d8", linewidth=0.8, alpha=0.85)
        ax_gene.axvline(variant_x, color="#e729d8", linewidth=0.8, alpha=0.85)
    ax_pred.set_ylim(0, ymax)
    track_label_parts = [
        str(pred.iloc[0].get("biosample_name", "frontal cortex")),
        str(pred.iloc[0].get("strand", "")),
        str(pred.iloc[0].get("ontology_curie", CURVE_ONTOLOGY)),
        str(pred.iloc[0].get("Assay title", pred.iloc[0].get("name", "RNA-seq"))),
    ]
    track_label = " ".join(part for part in track_label_parts if part and part.lower() != "nan")
    ax_pred.set_ylabel("RNA\nprediction", fontsize=fs(7))
    ax_pred.set_title(
        f"Frontal cortex RNA_SEQ prediction: {track_label}",
        loc="left",
        fontsize=fs(8),
        fontweight="bold",
        pad=max(1.0, 2 * font_scale),
    )
    ax_pred.legend(loc="upper right", frameon=True, fontsize=fs(6.2))
    if is_clipped:
        ax_pred.text(
            0.01,
            0.90,
            f"axis clipped at P99.5; max={max_observed:.3g}",
            ha="left",
            va="top",
            transform=ax_pred.transAxes,
            fontsize=fs(6.2),
            color="#5f6368",
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 1.0, "pad": 1.0},
            zorder=10,
        )
    ax_pred.spines[["top", "right"]].set_visible(False)
    ax_pred.tick_params(axis="both", labelsize=fs(6.2), length=max(0.5, 2 * font_scale))
    ax_pred.grid(axis="y", color="#e7ebef", linewidth=0.5)

    ax_delta.axhline(0, color="#222222", linewidth=0.7)
    ax_delta.fill_between(x, 0, delta, where=delta >= 0, color="#B2182B", alpha=0.65, linewidth=0)
    ax_delta.fill_between(x, 0, delta, where=delta < 0, color="#2166AC", alpha=0.65, linewidth=0)
    ax_delta.plot(x, delta, color="#4b5563", linewidth=0.45, alpha=0.65)
    ax_delta.set_yscale("symlog", linthresh=delta_linthresh)
    ax_delta.set_ylim(delta_ymin, delta_ymax)
    if np.isfinite(delta_min) and np.isfinite(delta_max):
        ax_delta.set_yticks([delta_min, 0.0, delta_max])
        ax_delta.set_yticklabels([f"{delta_min:.2g}", "0", f"{delta_max:.2g}"])
        ax_delta.minorticks_off()
    ax_delta.set_ylabel("ΔRNA\nALT−REF", fontsize=fs(7))
    ax_delta.text(
        0.01,
        0.88,
        f"symlog; min={delta_min:.3g}; max={delta_max:.3g}",
        ha="left",
        va="top",
        transform=ax_delta.transAxes,
        fontsize=fs(6.2),
        color="#5f6368",
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 1.0, "pad": 1.0},
        zorder=10,
    )
    ax_delta.spines[["top", "right"]].set_visible(False)
    ax_delta.tick_params(axis="both", labelsize=fs(6.2), length=max(0.5, 2 * font_scale))
    ax_delta.grid(axis="y", color="#e7ebef", linewidth=0.5)

    ax_gene.set_ylim(0, 1)
    ax_gene.axis("off")
    if not gene.empty and {"feature", "start", "end", "strand"}.issubset(gene.columns):
        gene_name = str(gene["gene_name"].dropna().iloc[0]) if gene["gene_name"].notna().any() else str(payload_summary.get("gene_symbol", "Gene"))
        strand = str(gene["strand"].dropna().iloc[0]) if gene["strand"].notna().any() else "."
        starts = pd.to_numeric(gene["start"], errors="coerce")
        ends = pd.to_numeric(gene["end"], errors="coerce")
        if starts.notna().any() and ends.notna().any():
            gene_start = max(plot_start, float(starts.min()) / 1e6)
            gene_end = min(plot_end, float(ends.max()) / 1e6)
            ax_gene.hlines(0.45, gene_start, gene_end, color="#111111", linewidth=1.4)
            exons = gene[gene["feature"].astype(str).eq("exon")].copy()
            for row in exons.itertuples(index=False):
                start = max(plot_start, float(getattr(row, "start")) / 1e6)
                end = min(plot_end, float(getattr(row, "end")) / 1e6)
                if end <= plot_start or start >= plot_end or end <= start:
                    continue
                ax_gene.add_patch(
                    plt.Rectangle(
                        (start, 0.32),
                        end - start,
                        0.26,
                        facecolor="#111111",
                        edgecolor="#111111",
                        linewidth=0.4,
                    )
                )
            arrow_count = 4
            for pos in np.linspace(gene_start, gene_end, arrow_count + 2)[1:-1]:
                dx = (plot_end - plot_start) * 0.018
                if strand == "-":
                    xy = (pos - dx, 0.45)
                    xytext = (pos + dx, 0.45)
                else:
                    xy = (pos + dx, 0.45)
                    xytext = (pos - dx, 0.45)
                ax_gene.annotate(
                    "",
                    xy=xy,
                    xytext=xytext,
                    arrowprops={"arrowstyle": "->", "color": "#111111", "lw": 0.8},
                )
            ax_gene.text(gene_start, 0.78, gene_name, color="#e729d8", fontsize=fs(8), fontstyle="italic", fontweight="bold")

    ax_pred.tick_params(axis="x", labelbottom=False)
    mb_span = plot_end - plot_start
    tick_decimals = 4 if mb_span < 0.01 else 3 if mb_span < 0.08 else 2
    ax_delta.xaxis.set_major_formatter(lambda value, _: f"{value:.{tick_decimals}f}")
    ax_delta.set_xlabel(f"{str(payload_summary.get('chrom', 'chr'))} (Mb)", fontsize=fs(7), labelpad=max(0.5, 1 * font_scale))
    return True


DEFAULT_SINGLE_FIGURE_WIDTH_MM = 10.5 * 25.4
DEFAULT_SINGLE_FIGURE_HEIGHT_MM = 8.35 * 25.4
DEFAULT_SINGLE_FONT_SIZE_PT = 6.0
REFERENCE_SINGLE_FONT_SIZE_PT = 7.5


def _font_scale(font_size_pt: float | None, reference_pt: float = REFERENCE_SINGLE_FONT_SIZE_PT) -> float:
    if font_size_pt is None:
        value = DEFAULT_SINGLE_FONT_SIZE_PT
    else:
        try:
            value = float(font_size_pt)
        except (TypeError, ValueError):
            value = DEFAULT_SINGLE_FONT_SIZE_PT
    return max(0.12, min(3.0, value / reference_pt))


def _svg_viewbox_size(svg: str) -> tuple[float, float] | None:
    match = re.search(r'viewBox="\\s*[-0-9.]+\\s+[-0-9.]+\\s+([0-9.]+)\\s+([0-9.]+)\\s*"', svg)
    if not match:
        return None
    try:
        return float(match.group(1)), float(match.group(2))
    except ValueError:
        return None


def _clamp_panel_mm(value: float | None, *, default: float, lower: float = 8.0, upper: float = 260.0) -> float:
    if value is None:
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(lower, min(upper, parsed))


def finite_float(value: object) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def display_variant_label(gene_symbol: object, variant_group_id: object) -> str:
    gene = str(gene_symbol or "Gene").strip() or "Gene"
    variant = str(variant_group_id or "").strip()
    if not variant:
        return gene
    for prefix in (f"{gene}_", f"{gene}-", f"{gene}."):
        if variant.startswith(prefix):
            suffix = variant[len(prefix) :].strip("_-.")
            return f"{gene} {suffix}" if suffix else gene
    if variant == gene:
        return gene
    return f"{gene} {variant}"


def render_prediction_panel_inline_svg(
    *,
    prediction_path: Path,
    gene_model_path: Path,
    payload_summary: dict[str, Any],
    figure_width_mm: float | None = None,
    figure_height_mm: float | None = None,
    font_size_pt: float | None = None,
    panel_height_mm: float | None = None,
) -> str:
    width_mm = float(figure_width_mm or DEFAULT_SINGLE_FIGURE_WIDTH_MM)
    height_mm = float(figure_height_mm or DEFAULT_SINGLE_FIGURE_HEIGHT_MM)
    resolved_panel_height_mm = _clamp_panel_mm(panel_height_mm, default=max(46.0, min(95.0, height_mm * 0.33)))
    scale = _font_scale(font_size_pt)
    fig = plt.figure(figsize=(width_mm / 25.4, resolved_panel_height_mm / 25.4))
    gs = fig.add_gridspec(3, 1, height_ratios=[0.48, 0.87, 0.87], hspace=0.34)
    ax_gene = fig.add_subplot(gs[0])
    ax_pred = fig.add_subplot(gs[1], sharex=ax_gene)
    ax_delta = fig.add_subplot(gs[2], sharex=ax_gene)
    plot_frontal_cortex_prediction_axes(
        ax_gene,
        ax_pred,
        ax_delta,
        prediction_path=prediction_path,
        gene_model_path=gene_model_path,
        payload_summary=payload_summary,
        font_scale=scale,
    )
    fig.subplots_adjust(left=0.105, right=0.985, top=0.94, bottom=0.16, hspace=0.34)
    buf = io.StringIO()
    fig.savefig(buf, format="svg")
    plt.close(fig)
    svg = buf.getvalue()
    svg = re.sub(r"<\?xml[^>]*>\s*", "", svg)
    svg = re.sub(r"<!DOCTYPE[^>]*>\s*", "", svg)
    return svg


def make_plot(
    source_table: Path,
    group_summary: Path,
    summary: dict[str, Any],
    html_out: Path,
    *,
    figure_width_mm: float | None = None,
    figure_height_mm: float | None = None,
    font_size_pt: float | None = None,
    top_panel_height_mm: float | None = None,
    effect_panel_height_mm: float | None = None,
    download_query: str = "",
) -> dict[str, Path]:
    tracks = pd.read_csv(source_table, sep="\t")
    groups = pd.read_csv(group_summary, sep="\t")
    tracks["effect"] = pd.to_numeric(tracks["effect"], errors="coerce")
    groups["median_effect"] = pd.to_numeric(groups["median_effect"], errors="coerce")
    groups = groups.set_index("display_group").reindex([g for g, _ in FULL_GROUP_ORDER]).reset_index()
    groups["short_label"] = [label for _, label in FULL_GROUP_ORDER]
    groups["n_tracks"] = groups["n_tracks"].fillna(0).astype(int)
    x_labels = [f"{r.short_label}\n({r.n_tracks})" for r in groups.itertuples(index=False)]
    x_positions = list(range(len(groups)))
    position = {group: i for i, (group, _) in enumerate(FULL_GROUP_ORDER)}
    prediction_path = source_table.parent / "frontal_cortex_prediction.tsv"
    gene_model_path = source_table.parent / "gene_model.tsv"

    width_mm = float(figure_width_mm or DEFAULT_SINGLE_FIGURE_WIDTH_MM)
    height_mm = float(figure_height_mm or DEFAULT_SINGLE_FIGURE_HEIGHT_MM)
    scale = _font_scale(font_size_pt)
    top_height = _clamp_panel_mm(top_panel_height_mm, default=max(42.0, min(92.0, height_mm * 0.36)))
    effect_height = _clamp_panel_mm(effect_panel_height_mm, default=max(30.0, height_mm - top_height - 16.0))
    fig = plt.figure(figsize=(width_mm / 25.4, height_mm / 25.4))
    top_total = max(1.0, top_height)
    gs = fig.add_gridspec(
        4,
        1,
        height_ratios=[top_total * 0.19, top_total * 0.405, top_total * 0.405, effect_height],
        hspace=0.92,
    )
    ax_gene = fig.add_subplot(gs[0])
    ax_top = fig.add_subplot(gs[1], sharex=ax_gene)
    ax_delta = fig.add_subplot(gs[2], sharex=ax_gene)
    ax = fig.add_subplot(gs[3])
    plot_summary = dict(summary)
    plot_frontal_cortex_prediction_axes(
        ax_gene,
        ax_top,
        ax_delta,
        prediction_path=prediction_path,
        gene_model_path=gene_model_path,
        payload_summary=plot_summary,
        font_scale=scale,
    )
    ax_delta.set_xlabel(f"GRCh38 {summary.get('chrom', '')} position (Mb)", fontsize=6.0 * scale)
    bar_colors = [
        "#B2182B" if value > 0 else "#2166AC" if value < 0 else "#BDBDBD"
        for value in groups["median_effect"].fillna(0)
    ]

    ax.bar(
        x_positions,
        groups["median_effect"],
        color=bar_colors,
        edgecolor="#222222",
        linewidth=0.6,
        alpha=0.86,
        label="Group median",
    )
    rng = np.random.default_rng(20260604)
    for row in tracks.itertuples(index=False):
        base = position.get(str(row.display_group))
        if base is None or not np.isfinite(row.effect):
            continue
        ax.scatter(
            base + float(rng.uniform(-0.22, 0.22)),
            float(row.effect),
            s=13,
            color="#B2182B" if row.effect > 0 else "#2166AC",
            alpha=0.58,
            edgecolors="none",
        )
    ax.axhline(0, color="#222222", lw=0.8)
    for boundary in PLOT_SECTION_BOUNDARIES:
        ax.axvline(boundary, color="#444444", lw=0.7)
    for section in PLOT_SECTION_LABELS:
        ax.text(
            (float(section["start"]) + float(section["end"])) / 2,
            0.985,
            str(section["label"]),
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="top",
            fontsize=5.6 * scale,
            color="#5f6368",
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.82, "pad": 0.3},
            clip_on=False,
        )
    title = f"{display_variant_label(summary.get('gene_symbol', 'Gene'), summary.get('variant_group_id', ''))}: matched-null-adjusted RNA log fold change"
    consensus_value = finite_float(summary.get("real_consensus_delta"))
    p_value = finite_float(summary.get("empirical_p_two_sided"))
    consensus_text = f"{consensus_value:.4f}" if consensus_value is not None else "NA"
    p_text = f"{p_value:.4g}" if p_value is not None else "NA"
    input_length = finite_float(summary.get("sequence_length"))
    input_text = f"{int(input_length):,} bp" if input_length is not None else "NA"
    subtitle = (
        f"run_mode={summary.get('run_mode', 'unknown')}; "
        f"Brain9 consensus={consensus_text}; "
        f"two-sided empirical P={p_text}; input={input_text}; "
        f"complete nulls={summary.get('n_null_consensus', 'NA')}"
    )
    ax.set_title(f"{title}\n{subtitle}", loc="left", fontsize=7.0 * scale, fontweight="bold", pad=9 * scale)
    ax.set_ylabel("Adjusted RNA log fold change", fontsize=8 * scale)
    ax.set_xlabel("Tissue/cell group", fontsize=8 * scale, labelpad=16 * scale)
    ax.set_xticks(x_positions)
    ax.set_xticklabels(x_labels, rotation=40, ha="right", fontsize=8 * scale)
    ax.tick_params(axis="y", labelsize=7.5 * scale)
    finite = tracks["effect"].dropna().to_numpy(dtype=float)
    if finite.size:
        max_abs = max(0.05, float(np.max(np.abs(finite))))
        ax.set_ylim(-max_abs * 1.22, max_abs * 1.22)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#e1e5ea", linewidth=0.6)
    ax.set_axisbelow(True)
    ax.text(
        0.995,
        0.02,
        "Bar = group median; dots = RNA-seq tracks; red/blue = positive/negative adjusted effect",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=7 * scale,
        color="#555555",
    )
    fig.subplots_adjust(left=0.105, right=0.985, top=0.94, bottom=0.19, hspace=1.05)
    label = figure_provenance_label(summary)
    if (summary.get('frontal_cortex_prediction_status') or {}).get('visualization_alignment', {}).get('version'):
        label += ' | RNA curves REF-coordinate aligned'
    fig.text(0.105, 0.025, label, fontsize=5.0 * scale, color='#666666', ha='left', va='bottom')
    html_out.parent.mkdir(parents=True, exist_ok=True)
    png_out = html_out.with_suffix(".png")
    svg_out = html_out.with_suffix(".svg")
    pdf_out = html_out.with_suffix(".pdf")
    fig.savefig(png_out, dpi=600)
    fig.savefig(svg_out)
    fig.savefig(pdf_out)
    plt.close(fig)

    interactive_groups: list[dict[str, Any]] = []
    for i, row in enumerate(groups.itertuples(index=False)):
        median_effect = safe_json_float(getattr(row, "median_effect", None))
        interactive_groups.append(
            {
                "x": i,
                "display_group": str(getattr(row, "display_group", "")),
                "label": str(getattr(row, "short_label", "")),
                "n_tracks": int(getattr(row, "n_tracks", 0)),
                "median_effect": median_effect,
            }
        )

    interactive_points: list[dict[str, Any]] = []
    rng = np.random.default_rng(20260604)
    for row in tracks.itertuples(index=False):
        base = position.get(str(row.display_group))
        if base is None or not np.isfinite(row.effect):
            continue
        interactive_points.append(
            {
                "x": base + float(rng.uniform(-0.22, 0.22)),
                "group_x": base,
                "effect": float(row.effect),
                "display_group": str(getattr(row, "display_group", "")),
                "track_scope": str(getattr(row, "track_scope", "")),
                "track_name": str(getattr(row, "track_name", "")),
                "biosample_name": str(getattr(row, "biosample_name", "")),
                "biosample_type": str(getattr(row, "biosample_type", "")),
                "ontology_curie": str(getattr(row, "ontology_curie", "")),
                "data_source": str(getattr(row, "data_source", "")),
                "raw_score": first_safe_json_float(row, "raw_score", "raw_delta_rna"),
                "null_median": first_safe_json_float(row, "null_median"),
            }
        )
    prediction_svg = render_prediction_panel_inline_svg(
        prediction_path=prediction_path,
        gene_model_path=gene_model_path,
        payload_summary=plot_summary,
        figure_width_mm=width_mm,
        figure_height_mm=height_mm,
        font_size_pt=font_size_pt,
        panel_height_mm=top_height,
    )
    query_suffix = f"?{download_query}" if download_query else ""
    html_font_px = max(1.0, float(font_size_pt or DEFAULT_SINGLE_FONT_SIZE_PT) * 96.0 / 72.0)
    effect_axis_px = max(90, int(round(effect_height / 25.4 * 96.0)))
    layout_scale = max(0.65, min(1.35, scale))
    viewbox_size = _svg_viewbox_size(prediction_svg)
    effect_view_width = float(viewbox_size[0]) if viewbox_size else float(width_mm / 25.4 * 72.0)
    viewbox_unit_scale = effect_view_width / 1120.0
    effect_top_base = max(48, int(round(74 * layout_scale)))
    effect_bottom_base = max(142, int(round(190 * layout_scale)))
    effect_margin = {
        "left": 126 * viewbox_unit_scale,
        "right": 24 * viewbox_unit_scale,
        "top": effect_top_base * viewbox_unit_scale,
        "bottom": effect_bottom_base * viewbox_unit_scale,
    }
    effect_panel_px = (effect_axis_px + effect_top_base + effect_bottom_base) * viewbox_unit_scale

    payload = {
        "title": title,
        "subtitle": subtitle,
        "groups": interactive_groups,
        "points": interactive_points,
        "y_min": float(ax.get_ylim()[0]) if "ax" in locals() else -0.2,
        "y_max": float(ax.get_ylim()[1]) if "ax" in locals() else 0.2,
        "font_scale": scale,
        "effect_axis_px": effect_axis_px,
        "effect_view_width": effect_view_width,
        "viewbox_unit_scale": viewbox_unit_scale,
        "effect_margin": effect_margin,
        "effect_panel_px": effect_panel_px,
        "section_boundaries": list(PLOT_SECTION_BOUNDARIES),
        "sections": list(PLOT_SECTION_LABELS),
        "brain_tissue_groups": list(BRAIN_TISSUE_GROUPS),
    }
    payload_json = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    html_out.write_text(
        f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{summary.get('gene_symbol', 'Gene')} AlphaGenome RNA effect</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #202124; }}
    main {{ padding: 16px 18px 8px; }}
    .plot-shell {{ max-width: 1040px; margin: 0 auto; }}
    .downloads a {{ display: inline-block; margin: 0 12px 14px 0; color: #2166ac; font-weight: 650; text-decoration: none; }}
    .toolbar {{ display: flex; flex-wrap: wrap; gap: 8px 14px; align-items: center; margin-bottom: 12px; color: #444; font-size: 13px; }}
    .toolbar label {{ display: inline-flex; gap: 5px; align-items: center; }}
    .toolbar button {{ border: 1px solid #cfd6de; background: #f7f9fc; border-radius: 6px; padding: 5px 9px; cursor: pointer; }}
    .prediction-panel {{ width: 100%; overflow: hidden; border: 1px solid #d8dde3; border-radius: 8px; padding: 14px 16px 16px; margin-bottom: 14px; box-sizing: border-box; background: #fff; }}
    .prediction-panel svg {{ width: 100%; max-width: 100%; height: auto; display: block; }}
    .figure {{ position: relative; width: 100%; overflow: hidden; border: 1px solid #d8dde3; border-radius: 8px; padding: 14px 16px 16px; box-sizing: border-box; }}
    .figure svg {{ width: 100%; max-width: 100%; height: auto; aspect-ratio: {effect_view_width:.6g} / {effect_panel_px:.6g}; display: block; }}
    .axis text {{ fill: #333; }}
    .grid line {{ stroke: #e1e5ea; stroke-width: 1; }}
    .bar {{ stroke: #222; stroke-width: 0.8; opacity: 0.88; cursor: pointer; }}
    .point {{ opacity: 0.58; cursor: crosshair; }}
    .point.dimmed {{ opacity: 0.12; }}
    .bar.dimmed {{ opacity: 0.24; }}
    .tooltip {{
      position: absolute;
      pointer-events: none;
      display: none;
      max-width: 360px;
      padding: 9px 10px;
      border: 1px solid #cfd6de;
      border-radius: 8px;
      background: rgba(255,255,255,0.97);
      box-shadow: 0 8px 22px rgba(0,0,0,0.12);
      font-size: 12px;
      line-height: 1.35;
      z-index: 10;
    }}
    .note {{ margin: 8px 0 0; color: #5f6368; font-size: 13px; }}
  </style>
</head>
<body>
  <main>
    <div class=\"plot-shell\">
      <div class=\"downloads\">
        <a href=\"download/plot_png{query_suffix}\">PNG</a>
        <a href=\"download/plot_svg{query_suffix}\">SVG</a>
        <a href=\"download/plot_pdf{query_suffix}\">PDF</a>
        <a href=\"download/source_table\">source_table.tsv</a>
        <a href=\"download/group_summary\">group_summary.tsv</a>
        <a href=\"download/qc_summary\">qc_summary.md</a>
      </div>
      <div class=\"prediction-panel\">{prediction_svg}</div>
      <div class=\"toolbar\">
        <label><input id=\"brainOnly\" type=\"checkbox\" /> emphasize brain tissue groups</label>
        <label><input id=\"showPoints\" type=\"checkbox\" checked /> show RNA-seq tracks</label>
        <button id=\"resetView\" type=\"button\">Reset view</button>
        <span>Hover bars or points for exact values.</span>
      </div>
      <div class=\"figure\">
        <svg id=\"effectPlot\" role=\"img\" aria-label=\"Interactive AlphaGenome RNA effect plot\"></svg>
        <div id=\"tooltip\" class=\"tooltip\"></div>
      </div>
      <p class=\"note\">Effect is the GeneMaskLFC score minus its trackwise matched-null median, reported as adjusted predicted RNA log fold change. It is not a measured percent expression change. Two-sided tests are primary; observed-direction one-sided results in the source tables are exploratory.</p>
    </div>
  </main>
  <script id=\"plotData\" type=\"application/json\">{payload_json}</script>
  <script>
{textwrap.dedent(r'''
const data = JSON.parse(document.getElementById('plotData').textContent);
const svg = document.getElementById('effectPlot');
const tooltip = document.getElementById('tooltip');
const brainOnly = document.getElementById('brainOnly');
const showPoints = document.getElementById('showPoints');
const resetView = document.getElementById('resetView');
const brainGroups = new Set(data.brain_tissue_groups || []);
const FONT_SCALE = Number(data.font_scale || 1);
function fs(value) { return Math.max(1, value * FONT_SCALE); }
const W = Number(data.effect_view_width || 1120), H = Number(data.effect_panel_px || 380);
const U = Number(data.viewbox_unit_scale || (W / 1120));
function u(value) { return value * U; }
const margin = data.effect_margin || {left: 118, right: 17, top: 64, bottom: 132};
let selectedGroup = null;
svg.setAttribute('viewBox', `0 0 ${W} ${H}`);

function xScale(x) {
  const n = data.groups.length;
  return margin.left + (x + 0.5) * ((W - margin.left - margin.right) / n);
}
function yScale(y) {
  return margin.top + (data.y_max - y) * ((H - margin.top - margin.bottom) / (data.y_max - data.y_min));
}
function fmt(value, digits=4) {
  if (value === null || Number.isNaN(value)) return 'NA';
  return Number(value).toFixed(digits);
}
function color(value) {
  if (value > 0) return '#B2182B';
  if (value < 0) return '#2166AC';
  return '#BDBDBD';
}
function elem(name, attrs={}, text=null) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', name);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text !== null) node.textContent = text;
  return node;
}
function showTip(event, html) {
  tooltip.innerHTML = html;
  tooltip.style.display = 'block';
  const box = event.currentTarget.ownerSVGElement.getBoundingClientRect();
  tooltip.style.left = `${event.clientX - box.left + 18}px`;
  tooltip.style.top = `${event.clientY - box.top + 18}px`;
}
function hideTip() {
  tooltip.style.display = 'none';
}
function shouldDim(group) {
  if (selectedGroup && group !== selectedGroup) return true;
  if (brainOnly.checked && !brainGroups.has(group)) return true;
  return false;
}
function render() {
  svg.replaceChildren();
  svg.appendChild(elem('rect', {x: 0, y: 0, width: W, height: H, fill: '#fff'}));
  svg.appendChild(elem('text', {x: margin.left, y: u(22), 'font-size': fs(6.8), 'font-weight': 700}, data.title));
  svg.appendChild(elem('text', {x: margin.left, y: u(40), 'font-size': fs(5.3), 'font-weight': 650}, data.subtitle));

  const plotW = W - margin.left - margin.right;
  const plotH = H - margin.top - margin.bottom;
  const zeroY = yScale(0);
  const yTicks = [-0.15, -0.10, -0.05, 0, 0.05, 0.10, 0.15].filter(v => v >= data.y_min && v <= data.y_max);
  const grid = elem('g', {class: 'grid'});
  for (const tick of yTicks) {
    const y = yScale(tick);
    grid.appendChild(elem('line', {x1: margin.left, x2: W - margin.right, y1: y, y2: y}));
    grid.appendChild(elem('text', {x: margin.left - u(12), y: y + u(3), 'text-anchor': 'end', 'font-size': fs(5.6), fill: '#333'}, fmt(tick, 2)));
  }
  svg.appendChild(grid);
  svg.appendChild(elem('line', {x1: margin.left, x2: W - margin.right, y1: zeroY, y2: zeroY, stroke: '#222', 'stroke-width': 1.2}));
  svg.appendChild(elem('line', {x1: margin.left, x2: margin.left, y1: margin.top, y2: H - margin.bottom, stroke: '#222', 'stroke-width': 1.1}));
  svg.appendChild(elem('line', {x1: margin.left, x2: W - margin.right, y1: H - margin.bottom, y2: H - margin.bottom, stroke: '#222', 'stroke-width': 1.1}));
  for (const boundary of data.section_boundaries || []) {
    svg.appendChild(elem('line', {x1: xScale(boundary), x2: xScale(boundary), y1: margin.top, y2: H - margin.bottom, stroke: '#555', 'stroke-width': 1}));
  }
  for (const section of data.sections || []) {
    const center = (Number(section.start) + Number(section.end)) / 2;
    svg.appendChild(elem('text', {x: xScale(center), y: margin.top - u(10), 'text-anchor': 'middle', 'font-size': fs(4.9), fill: '#5f6368'}, section.label));
  }

  const barWidth = plotW / data.groups.length * 0.72;
  for (const g of data.groups) {
    if (g.median_effect === null) continue;
    const x = xScale(g.x) - barWidth / 2;
    const y0 = yScale(0);
    const y1 = yScale(g.median_effect);
    const bar = elem('rect', {
      class: `bar ${shouldDim(g.display_group) ? 'dimmed' : ''}`,
      x, y: Math.min(y0, y1),
      width: barWidth,
      height: Math.max(1, Math.abs(y1 - y0)),
      fill: color(g.median_effect)
    });
    bar.addEventListener('mousemove', ev => showTip(ev, `<b>${g.display_group}</b><br>median adjusted RNA log fold change=${fmt(g.median_effect)}<br>n tracks=${g.n_tracks}<br><i>click to highlight group</i>`));
    bar.addEventListener('mouseleave', hideTip);
    bar.addEventListener('click', () => { selectedGroup = selectedGroup === g.display_group ? null : g.display_group; render(); });
    svg.appendChild(bar);
  }

  if (showPoints.checked) {
    for (const p of data.points) {
      const point = elem('circle', {
        class: `point ${shouldDim(p.display_group) ? 'dimmed' : ''}`,
        cx: xScale(p.x),
        cy: yScale(p.effect),
        r: u(2.8),
        fill: color(p.effect)
      });
      point.addEventListener('mousemove', ev => showTip(ev, `<b>${p.biosample_name}</b><br>${p.track_name}<br>group=${p.display_group}<br>adjusted RNA log fold change=${fmt(p.effect, 5)}<br>raw GeneMaskLFC score=${fmt(p.raw_score, 5)}<br>null median=${fmt(p.null_median, 5)}<br>source=${p.data_source}`));
      point.addEventListener('mouseleave', hideTip);
      svg.appendChild(point);
    }
  }

  const axis = elem('g', {class: 'axis'});
  for (const g of data.groups) {
    const tx = elem('text', {
      x: xScale(g.x),
      y: H - margin.bottom + u(18),
      'text-anchor': 'end',
      'font-size': fs(5.4),
      transform: `rotate(-38 ${xScale(g.x)} ${H - margin.bottom + u(18)})`
    }, `${g.label} (${g.n_tracks})`);
    axis.appendChild(tx);
  }
  axis.appendChild(elem('text', {x: u(24), y: margin.top + plotH / 2, transform: `rotate(-90 ${u(24)} ${margin.top + plotH / 2})`, 'text-anchor': 'middle', 'font-size': fs(5.8), 'font-weight': 650}, 'Adjusted RNA log fold change'));
  axis.appendChild(elem('text', {x: margin.left + plotW / 2, y: H - u(18), 'text-anchor': 'middle', 'font-size': fs(5.8), 'font-weight': 650}, 'Tissue/cell group'));
  svg.appendChild(axis);
  svg.appendChild(elem('text', {x: W - margin.right, y: H - margin.bottom - u(9), 'text-anchor': 'end', 'font-size': fs(4.8), fill: '#666'}, 'Bar = group median; dots = RNA-seq tracks; red/blue = positive/negative adjusted effect'));
}
brainOnly.addEventListener('change', render);
showPoints.addEventListener('change', render);
resetView.addEventListener('click', () => { selectedGroup = null; brainOnly.checked = false; showPoints.checked = true; render(); });
render();
''')}
  </script>
</body>
</html>
""",
    )
    return {"plot_png": png_out, "plot_svg": svg_out, "plot_pdf": pdf_out}


def write_qc_summary(path: Path, payload: dict[str, Any], summary: dict[str, Any], mode: str) -> None:
    text = f"""# Single-Variant Job QC Summary

## Input

```text
variant_group_id: {payload.get('variant_group_id')}
gene_symbol: {payload.get('gene_symbol')}
chrom: {payload.get('chrom')}
pos1: {payload.get('pos1')}
ref: {payload.get('ref')}
alt: {payload.get('alt')}
target_gene: {payload.get('target_gene') or payload.get('gene_symbol')}
run_mode: {mode}
```

## Result

```text
api_called: {summary.get('api_called')}
effect_definition: {summary.get('effect_definition')}
n_real_brain_tracks: {summary.get('n_real_brain_tracks')}
n_real_primary_brain_tissue_groups: {summary.get('n_real_brain_groups')}
n_null_consensus: {summary.get('n_null_consensus')}
consensus_brain_adjusted_rna_log_fold_change: {summary.get('real_consensus_delta')}
empirical_p_two_sided: {summary.get('empirical_p_two_sided')}
single_variant_multiple_testing_family_size: 1
observed_direction_one_sided_status: exploratory
primary_effect_scope: {summary.get('primary_effect_scope')}
classification_version: {summary.get('classification', {}).get('version')}
primary_brain_coverage: {json.dumps(summary.get('primary_brain_coverage', {}), sort_keys=True)}
```

The reported effect is the GeneMaskLFC score minus its trackwise matched-null
median, expressed as adjusted predicted RNA log fold change. The documented
GeneMaskLFC formula is log(mean(ALT) + 0.001) - log(mean(REF) + 0.001),
evaluated over the gene exon mask; the logarithm base is not specified here.
The plotted value is not a measured percent expression change.
The separate position-wise REF/ALT prediction panel shows the direct difference
between RNA prediction tracks and does not use the GeneMaskLFC score.
Two-sided tests are primary. Observed-direction one-sided tests are exploratory;
the direction was selected from the observed effect, not prespecified.
Single-variant displays report the empirical P value without a multi-variant
correction. Legacy bh_fdr fields equal P for this one-test family. Multi-variant
summaries apply Benjamini-Hochberg correction across the complete requested family.
Brain9 is the median of eight adult-category medians and one pooled embryonic
brain-tissue median. Non-brain tissues and cells/lines are display-only pools.
The target-vs-neighbor QC uses all-track raw scores, not Brain9-adjusted effects.
"""
    write_text(path, text)


def run_command(
    cmd: list[str],
    cwd: Path,
    log_path: Path,
    env: dict[str, str] | None = None,
    line_callback: Callable[[str], None] | None = None,
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    run_env = dict(env or os.environ.copy())
    run_env.setdefault("PYTHONUNBUFFERED", "1")
    with log_path.open("a") as log:
        log.write("$ " + " ".join(cmd) + "\n")
        log.flush()
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=run_env,
            pass_fds=(int(run_env["AG_LOCAL_RUN_LOCK_FD"]),) if "AG_LOCAL_RUN_LOCK_FD" in run_env else (),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            line = redact(line)
            log.write(line)
            log.flush()
            if line_callback is not None:
                line_callback(line.rstrip("\n"))
        proc.wait()
        proc.stdout.close()
        if proc.returncode != 0:
            raise RuntimeError(f"command failed with exit code {proc.returncode}: {' '.join(cmd)}")


def complete_primary_brain_consensus(
    group_summary: pd.DataFrame,
    null_effects: pd.DataFrame,
    *,
    all_null_ids: list[str],
    requested_null_depth: int | None,
    coverage_out: Path,
) -> tuple[np.ndarray, pd.Series, dict[str, Any]]:
    """Require nine real groups and use only nine-group-complete null variants."""
    real = group_summary.set_index("display_group")["median_effect"].reindex(BRAIN_TISSUE_GROUPS)
    real = pd.to_numeric(real, errors="coerce")
    real_finite = np.isfinite(real.to_numpy(dtype=float))
    missing_real = real.index[~real_finite].tolist()
    null_brain = null_effects[null_effects["display_group"].isin(PRIMARY_BRAIN_TISSUE_GROUPS)].copy()
    null_brain["null_id"] = null_brain["null_id"].astype(str)
    if null_brain.empty:
        null_matrix = pd.DataFrame(index=all_null_ids, columns=BRAIN_TISSUE_GROUPS, dtype=float)
    else:
        null_matrix = null_brain.groupby(["null_id", "display_group"])["effect"].median().unstack()
        null_matrix = null_matrix.reindex(index=all_null_ids, columns=BRAIN_TISSUE_GROUPS)
    finite_groups = np.isfinite(null_matrix.to_numpy(dtype=float)).sum(axis=1)
    complete = finite_groups == len(BRAIN_TISSUE_GROUPS)
    complete_ids = null_matrix.index[complete].tolist()
    incomplete_ids = null_matrix.index[~complete].tolist()
    # All values in these rows are finite, so no missing-group skip is possible.
    null_consensus = null_matrix.loc[complete_ids].median(axis=1)
    publication_depth = requested_null_depth is not None and requested_null_depth >= 1000
    requested_count_matches = requested_null_depth is None or len(complete_ids) == requested_null_depth
    failure_reasons = []
    if missing_real:
        failure_reasons.append("real effect is missing finite values for primary brain groups: " + ", ".join(missing_real))
    if not complete_ids:
        failure_reasons.append("no null variants have finite values in all nine primary brain groups")
    if publication_depth and (not requested_count_matches or incomplete_ids):
        failure_reasons.append(
            f"publication analysis requires {requested_null_depth} complete nine-group null variants; "
            f"observed {len(complete_ids)} complete and {len(incomplete_ids)} incomplete"
        )
    coverage = {
        "status": "failed" if failure_reasons else "warning" if incomplete_ids or not requested_count_matches else "passed",
        "required_groups": list(BRAIN_TISSUE_GROUPS),
        "required_group_count": len(BRAIN_TISSUE_GROUPS),
        "n_real_complete_groups": int(real_finite.sum()),
        "missing_real_groups": missing_real,
        "requested_null_depth": requested_null_depth,
        "n_null_ids_observed": len(all_null_ids),
        "n_null_complete": len(complete_ids),
        "n_null_incomplete": len(incomplete_ids),
        "excluded_incomplete_null_ids": incomplete_ids,
        "null_group_count_distribution": {
            str(n): int(np.sum(finite_groups == n)) for n in range(len(BRAIN_TISSUE_GROUPS) + 1)
        },
        "publication_depth_required": publication_depth,
        "publication_depth_passed": publication_depth and not failure_reasons,
        "complete_case_rule": "finite group median in every one of the nine primary brain groups (eight adult categories plus pooled embryonic brain tissue)",
        "failure_reasons": failure_reasons,
    }
    write_json(coverage_out, coverage)
    null_matrix.rename_axis("null_id").to_csv(
        coverage_out.parent / "null_group_medians.tsv", sep="\t", float_format="%.17g"
    )
    if failure_reasons:
        raise ValueError("; ".join(failure_reasons))
    return real.to_numpy(dtype=float), null_consensus, coverage


def copy_matched_null_design(
    payload: dict[str, Any], *, data_dir: Path, results_dir: Path
) -> Path | None:
    """Export the original sampled design without generating or modifying nulls."""
    variant_kind = infer_variant_class(payload["ref"], payload["alt"]).split("_", 1)[0]
    if variant_kind not in {"deletion", "insertion", "substitution"}:
        raise ValueError(f"Unsupported matched-null design class: {variant_kind}")
    source = data_dir / f"matched_{variant_kind}_nulls.tsv"
    destination = results_dir / "matched_null_design.tsv"
    if source.is_file():
        results_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return destination
    if destination.exists():
        # A missing current source must not leave a previous export masquerading
        # as the design used for the newly summarized scores.
        destination.rename(destination.with_name(f"{destination.name}.previous-{uuid.uuid4().hex}"))
    return None


def compute_from_scores(
    *,
    payload: dict[str, Any],
    v04_pipeline_dir: Path,
    real_scores: Path,
    null_scores: Path,
    results_dir: Path,
) -> dict[str, Any]:
    target = str(payload.get("target_gene") or payload["gene_symbol"]).upper()
    variant_group_id = str(payload["variant_group_id"])

    def read_target_score_rows(path: Path, *, chunksize: int = 250_000) -> pd.DataFrame:
        """Read only target-gene RNA score rows from potentially very large score TSVs."""
        header = pd.read_csv(path, sep="\t", nrows=0).columns.tolist()
        preferred = {
            "variant_id",
            "scored_interval",
            "gene_id",
            "gene_name",
            "gene_type",
            "gene_strand",
            "output_type",
            "variant_scorer",
            "track_name",
            "track_strand",
            "Assay title",
            "ontology_curie",
            "biosample_name",
            "biosample_type",
            "biosample_life_stage",
            "gtex_tissue",
            "data_source",
            "endedness",
            "genetically_modified",
            "raw_score",
            "quantile_score",
            "null_id",
            "variant_group_id",
            "deletion_length",
            "insertion_length",
            "indel_length",
            "gc_fraction",
            "fixed_interval",
            "variant_class",
            "representation",
            "sub_index",
            "chrom",
            "pos1",
            "ref",
            "alt",
        }
        usecols = [col for col in header if col in preferred]
        frames: list[pd.DataFrame] = []
        for chunk in pd.read_csv(path, sep="\t", usecols=usecols, chunksize=chunksize, low_memory=False, float_precision="round_trip", dtype={"null_id": str}):
            required = {"variant_group_id", "output_type", "variant_scorer", "gene_name"}
            if not required.issubset(chunk.columns):
                missing = ", ".join(sorted(required - set(chunk.columns)))
                raise ValueError(f"{path} is missing required score columns: {missing}")
            mask = (
                chunk["variant_group_id"].astype(str).eq(variant_group_id)
                & chunk["output_type"].astype(str).eq("RNA_SEQ")
                & chunk["variant_scorer"].astype(str).str.startswith("GeneMaskLFCScorer")
                & chunk["gene_name"].astype(str).str.upper().eq(target)
            )
            if mask.any():
                frames.append(chunk.loc[mask].copy())
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=usecols)

    real = read_target_score_rows(real_scores)
    if real.empty:
        raise ValueError(f"no real RNA_SEQ target rows for {variant_group_id}/{target}")
    null = read_target_score_rows(null_scores)
    if null.empty:
        raise ValueError(f"no null RNA_SEQ target rows for {variant_group_id}/{target}")
    raw_real_rows, raw_null_rows = len(real), len(null)
    matched_design = copy_matched_null_design(payload, data_dir=null_scores.parent, results_dir=results_dir)
    if matched_design is None:
        raise ValueError("Fresh Brain9 analysis requires its original matched-null design for null ID verification")
    expected_null_ids = None
    if matched_design is not None:
        design = pd.read_csv(matched_design, sep="\t", dtype=str)
        if "null_id" not in design or design["null_id"].isna().any():
            raise ValueError("Matched-null design is missing null IDs")
        expected_null_ids = design["null_id"].tolist()
    requested_null_depth = int(payload["null_depth"]) if payload.get("null_depth") is not None else None
    real, null, classification_audit = canonicalize_scores(
        real, null, requested_null_depth=requested_null_depth,
        audit_out=results_dir / "classification_audit.json", expected_null_ids=expected_null_ids,
    )
    all_null_ids = sorted(null["null_id"].unique().tolist())

    group_rows = []
    for group, label in FULL_GROUP_ORDER:
        sub = real[real["display_group"].eq(group)]
        values = pd.to_numeric(sub["effect"], errors="coerce").dropna().to_numpy(dtype=float)
        n_tracks = int(sub["track_key"].nunique()) if not sub.empty else 0
        n_raw = int(sub["n_raw_effect_rows"].sum()) if "n_raw_effect_rows" in sub.columns and not sub.empty else 0
        group_rows.append(
            {
                "display_group": group,
                "included_in_brain9": group in PRIMARY_BRAIN_TISSUE_GROUPS,
                "label": f"{label} ({n_tracks})",
                "n_tracks": n_tracks,
                "n_raw_effect_rows": n_raw,
                "n_duplicate_effect_rows": int(n_raw - n_tracks),
                "median_effect": float(np.median(values)) if len(values) else np.nan,
                "mean_effect": float(np.mean(values)) if len(values) else np.nan,
                "min_effect": float(np.min(values)) if len(values) else np.nan,
                "max_effect": float(np.max(values)) if len(values) else np.nan,
            }
        )
    group_summary = pd.DataFrame(group_rows)
    requested_null_depth = int(payload["null_depth"]) if payload.get("null_depth") is not None else None
    brain_real, null_consensus, coverage = complete_primary_brain_consensus(
        group_summary,
        null,
        all_null_ids=all_null_ids,
        requested_null_depth=requested_null_depth,
        coverage_out=results_dir / "primary_brain_coverage.json",
    )
    real_consensus = float(np.median(brain_real))
    null_median = float(np.median(null_consensus.to_numpy(dtype=float)))
    null_mad = float(np.median(np.abs(null_consensus.to_numpy(dtype=float) - null_median)))
    denom = 1.4826 * null_mad if null_mad > 0 else np.nan
    consensus_z = float((real_consensus - null_median) / denom) if np.isfinite(denom) else np.nan
    centered = null_consensus - null_median
    real_centered = real_consensus - null_median
    p_two = float((1 + np.sum(np.abs(centered) >= abs(real_centered))) / (1 + len(centered)))
    if real_centered >= 0:
        p_obs = float((1 + np.sum(centered >= real_centered)) / (1 + len(centered)))
        direction = "increase"
    else:
        p_obs = float((1 + np.sum(centered <= real_centered)) / (1 + len(centered)))
        direction = "decrease"

    source_out = results_dir / "source_table.tsv"
    group_out = results_dir / "group_summary.tsv"
    real.to_csv(source_out, sep="\t", index=False)
    group_summary.to_csv(group_out, sep="\t", index=False)
    null_consensus.rename("consensus_effect").rename_axis("null_id").to_csv(
        results_dir / "null_consensus.tsv", sep="\t", float_format="%.17g"
    )
    reproducibility_source_files = {
        "null_consensus": "null_consensus.tsv",
        "null_group_medians": "null_group_medians.tsv",
        "classification_audit": "classification_audit.json",
        "classification_tracks": "classification_audit.tsv",
    }
    if matched_design is not None:
        reproducibility_source_files["matched_null_design"] = matched_design.name
    summary = {
        "variant_group_id": variant_group_id,
        "gene_symbol": payload["gene_symbol"],
        "variant_class": infer_variant_class(payload["ref"], payload["alt"]),
        "effect_definition": "GeneMaskLFC score minus trackwise matched-null median",
        "effect_units": "matched-null-adjusted predicted RNA log fold change",
        "logarithm_base": "not exposed by API client",
        "primary_effect_scope": BRAIN9_SCOPE,
        "classification": classification_provenance(),
        "classification_audit": classification_audit,
        "primary_effect_groups": list(BRAIN_TISSUE_GROUPS),
        "display_only_groups": list(DISPLAY_ONLY_GROUPS),
        "n_real_brain_tracks": int(real[real["display_group"].isin(PRIMARY_BRAIN_TISSUE_GROUPS)].shape[0]),
        "n_raw_real_effect_rows": raw_real_rows,
        "n_canonical_real_effect_rows": int(real.shape[0]),
        "n_duplicate_real_effect_rows": int(raw_real_rows - real.shape[0]),
        "n_real_brain_groups": int(len(brain_real)),
        "n_null_consensus": int(len(null_consensus)),
        "primary_brain_coverage": coverage,
        "reproducibility_source_files": reproducibility_source_files,
        "matched_null_design_available": matched_design is not None,
        "null_consensus_export_definition": "median across the nine primary-group null effects before consensus-null median centering",
        "n_raw_null_effect_rows": raw_null_rows,
        "n_canonical_null_effect_rows": int(null.shape[0]),
        "n_duplicate_null_effect_rows": int(raw_null_rows - null.shape[0]),
        "real_consensus_delta": real_consensus,
        "null_consensus_median": null_median,
        "null_consensus_mad": null_mad,
        "consensus_z": consensus_z,
        "direction_observed": direction,
        "empirical_p_two_sided": p_two,
        "empirical_p_observed_direction": p_obs,
        "bh_fdr_two_sided": p_two,
        "bh_fdr_observed_direction": p_obs,
        "primary_test": "two_sided",
        "observed_direction_one_sided_status": "exploratory_not_prespecified",
        "single_variant_multiple_testing_family_size": 1,
        "run_mode": "api_full",
        "api_called": True,
        "scoring_provenance": {
            "real": load_score_provenance(real_scores),
            "null": load_score_provenance(null_scores),
        },
    }
    write_json(results_dir / "consensus_summary.json", summary)
    return summary


def run_api_full(
    *,
    db_path: Path,
    job_id: str,
    payload: dict[str, Any],
    job_dir: Path,
    v04_pipeline_dir: Path,
    hg38_fasta: Path,
    gencode_gtf: Path,
    log_dir: Path,
) -> dict[str, Any]:
    if os.environ.get("AG_WEB_ENABLE_API_FULL", "0").strip() != "1":
        raise RuntimeError("api_full is disabled. Set AG_WEB_ENABLE_API_FULL=1 to allow API calls.")
    if not os.environ.get("ALPHA_GENOME_API_KEY", "").strip():
        raise RuntimeError("api_full requires ALPHA_GENOME_API_KEY in the server environment.")
    variant_class = infer_variant_class(payload["ref"], payload["alt"])
    if variant_class.startswith("insertion"):
        null_kind = "insertion"
        null_script = "04_generate_insertion_nulls.py"
        null_designs = job_dir / "data" / "matched_insertion_nulls.tsv"
    elif variant_class.startswith("deletion"):
        null_kind = "deletion"
        null_script = "02_generate_deletion_nulls.py"
        null_designs = job_dir / "data" / "matched_deletion_nulls.tsv"
    elif variant_class.startswith("substitution"):
        null_kind = "substitution"
        null_script = "03_generate_substitution_nulls.py"
        null_designs = job_dir / "data" / "matched_substitution_nulls.tsv"
    else:
        raise RuntimeError(f"unsupported variant_class for api_full: {variant_class}")
    input_tsv = job_dir / "input" / "variant.tsv"
    real_scores = job_dir / "data" / "real_scores.tsv"
    null_scores = job_dir / "data" / "null_scores.tsv"
    sequence_length = str(int(payload.get("sequence_length", 1_048_576)))
    null_depth = str(int(payload.get("null_depth", 10)))
    py = sys.executable
    inference_context = inference_identity(payload, gencode_gtf)
    subprocess_env = os.environ.copy()
    subprocess_env.update({
        "AG_INFERENCE_BACKEND_REVISION": inference_context["inference_backend_revision"],
        "AG_INFERENCE_RUN_EPOCH": inference_context["inference_run_epoch"],
        "AG_REQUESTED_MODEL_VERSION": inference_context["requested_model_version"],
        "GENCODE_GTF": str(gencode_gtf),
    })
    update_job(
        db_path,
        job_id,
        stage="score_real",
        message="Scoring the submitted variant with AlphaGenome RNA_SEQ",
        progress_percent=12,
    )
    run_command(
        [
            py,
            str(v04_pipeline_dir / "scripts" / "00_score_real_variants_rna.py"),
            "--variants",
            str(input_tsv),
            "--out",
            str(real_scores),
            "--sequence-length",
            sequence_length,
        ],
        cwd=v04_pipeline_dir,
        log_path=log_dir / "score_real.log",
        env=subprocess_env,
    )
    update_job(
        db_path,
        job_id,
        stage="target_gene_qc",
        message="Checking target-gene assignment and hg38 REF consistency",
        progress_percent=24,
    )
    run_command(
        [
            py,
            str(v04_pipeline_dir / "scripts" / "10_target_gene_assignment_qc.py"),
            "--variants",
            str(input_tsv),
            "--gtf",
            str(gencode_gtf),
            "--hg38",
            str(hg38_fasta),
            "--score-tsv",
            str(real_scores),
            "--sequence-length",
            sequence_length,
            "--out",
            str(job_dir / "results" / "target_gene_assignment_qc.tsv"),
            "--neighbor-out",
            str(job_dir / "results" / "target_vs_neighbor_gene_effects.tsv"),
            "--all-gene-out",
            str(job_dir / "results" / "all_gene_rna_effect_summary.tsv"),
        ],
        cwd=v04_pipeline_dir,
        log_path=log_dir / "target_gene_assignment_qc.log",
        env={k: v for k, v in subprocess_env.items() if k != "ALPHA_GENOME_API_KEY"},
    )
    update_job(
        db_path,
        job_id,
        stage="generate_nulls",
        message=f"Generating {null_depth} matched {null_kind} null variants",
        progress_percent=38,
    )
    run_command(
        [
            py,
            str(v04_pipeline_dir / "scripts" / null_script),
            "--variants",
            str(input_tsv),
            "--hg38",
            str(hg38_fasta),
            "--out",
            str(null_designs),
            "--per-group",
            null_depth,
            "--sequence-length",
            sequence_length,
        ],
        cwd=v04_pipeline_dir,
        log_path=log_dir / "generate_nulls.log",
        env={k: v for k, v in subprocess_env.items() if k != "ALPHA_GENOME_API_KEY"},
    )
    update_job(
        db_path,
        job_id,
        stage="score_nulls",
        message=f"Scoring {null_depth} matched {null_kind} null variants with AlphaGenome RNA_SEQ: 0/{null_depth}",
        progress_percent=65,
    )

    def update_null_progress(line: str) -> None:
        match = re.search(r"\bscored\s+(\d+)/(\d+)\b", line)
        if not match:
            return
        done = int(match.group(1))
        total = max(1, int(match.group(2)))
        fraction = max(0.0, min(1.0, done / total))
        pct = 65.0 + (88.0 - 65.0) * fraction
        update_job(
            db_path,
            job_id,
            stage="score_nulls",
            message=(
                f"Scoring {total} matched {null_kind} null variants with AlphaGenome RNA_SEQ: "
                f"{done}/{total} ({fraction * 100:.1f}%)"
            ),
            progress_percent=pct,
        )

    run_command(
        [
            py,
            str(v04_pipeline_dir / "scripts" / "05_score_null_rna.py"),
            "--pseudo",
            str(null_designs),
            "--variants",
            str(input_tsv),
            "--out",
            str(null_scores),
            "--sequence-length",
            sequence_length,
        ],
        cwd=v04_pipeline_dir,
        log_path=log_dir / "score_nulls.log",
        env=subprocess_env,
        line_callback=update_null_progress,
    )
    update_job(
        db_path,
        job_id,
        stage="summarize",
        message="Computing matched-null adjusted RNA effects",
        progress_percent=88,
    )
    return compute_from_scores(
        payload=payload,
        v04_pipeline_dir=v04_pipeline_dir,
        real_scores=real_scores,
        null_scores=null_scores,
        results_dir=job_dir / "results",
    )


def run_job(
    *,
    db_path: str,
    job_id: str,
    payload: dict[str, Any],
    run_mode: str,
    job_dir: str,
    v04_reference_run: str,
    v04_pipeline_dir: str,
    hg38_fasta: str,
    gencode_gtf: str,
) -> None:
    db = Path(db_path)
    root = Path(job_dir)
    results_dir = root / "results"
    log_dir = root / "logs"
    try:
        if run_mode != "api_full":
            raise ValueError("Local runner permits only fresh api_full jobs; no demo or legacy fallback")
        update_job(
            db,
            job_id,
            status="running",
            stage="write_inputs",
            message="Writing job inputs",
            progress_percent=5,
        )
        root.mkdir(parents=True, exist_ok=True)
        make_variant_tsv(root / "input" / "variant.tsv", payload)
        write_json(root / "input" / "run_config.json", {"run_mode": run_mode, **payload})

        if run_mode == "demo_cached":
            update_job(
                db,
                job_id,
                stage="load_demo",
                message="Loading cached publication-quality demo output",
                progress_percent=70,
            )
            summary = load_demo_outputs(payload, Path(v04_reference_run), results_dir)
        elif run_mode == "api_full":
            update_job(
                db,
                job_id,
                stage="api_full",
                message="Running guarded full AlphaGenome API workflow",
                progress_percent=12,
            )
            summary = run_api_full(
                db_path=db,
                job_id=job_id,
                payload=payload,
                job_dir=root,
                v04_pipeline_dir=Path(v04_pipeline_dir),
                hg38_fasta=Path(hg38_fasta),
                gencode_gtf=Path(gencode_gtf),
                log_dir=log_dir,
            )
        else:
            raise ValueError(f"unsupported run_mode: {run_mode}")

        summary.update(
            {
                "chrom": payload.get("chrom"),
                "pos1": payload.get("pos1"),
                "ref": payload.get("ref"),
                "alt": payload.get("alt"),
                "target_gene": payload.get("target_gene") or payload.get("gene_symbol"),
                "sequence_length": payload.get("sequence_length"),
            }
        )
        update_job(
            db,
            job_id,
            stage="predict_tracks",
            message="Predicting/caching Frontal cortex REF/ALT RNA_SEQ track",
            progress_percent=92,
        )
        if run_mode == "demo_cached":
            prediction_status = load_demo_prediction(payload, results_dir)
        else:
            prediction_status = ensure_frontal_cortex_prediction(
                payload=payload,
                results_dir=results_dir,
                cache_root=root.parent,
                gencode_gtf=Path(gencode_gtf),
            )
        summary["frontal_cortex_prediction_status"] = prediction_status
        write_json(results_dir / "consensus_summary.json", summary)

        update_job(
            db,
            job_id,
            stage="plot",
            message="Writing static Matplotlib plot",
            progress_percent=94,
        )
        plot_paths = make_plot(
            results_dir / "source_table.tsv",
            results_dir / "group_summary.tsv",
            summary,
            results_dir / "single_gene_plot.html",
        )
        write_qc_summary(results_dir / "qc_summary.md", payload, summary, run_mode)
        result = {
            "job_dir": str(root),
            "plot_html": str(results_dir / "single_gene_plot.html"),
            "plot_png": str(plot_paths["plot_png"]),
            "plot_svg": str(plot_paths["plot_svg"]),
            "plot_pdf": str(plot_paths["plot_pdf"]),
            "source_table": str(results_dir / "source_table.tsv"),
            "group_summary": str(results_dir / "group_summary.tsv"),
            "consensus_summary": str(results_dir / "consensus_summary.json"),
            "qc_summary": str(results_dir / "qc_summary.md"),
            "frontal_cortex_prediction": str(results_dir / "frontal_cortex_prediction.tsv"),
            "frontal_cortex_prediction_raw": str(results_dir / "frontal_cortex_prediction_raw.tsv"),
            "gene_model": str(results_dir / "gene_model.tsv"),
            "frontal_cortex_prediction_status": str(results_dir / "frontal_cortex_prediction_status.json"),
        }
        optional_artifacts = {
            "classification_audit": results_dir / "classification_audit.json",
            "classification_tracks": results_dir / "classification_audit.tsv",
            "null_consensus": results_dir / "null_consensus.tsv",
            "null_group_medians": results_dir / "null_group_medians.tsv",
            "matched_null_design": results_dir / "matched_null_design.tsv",
            "target_gene_assignment_qc": results_dir / "target_gene_assignment_qc.tsv",
            "target_vs_neighbor_gene_effects": results_dir / "target_vs_neighbor_gene_effects.tsv",
            "all_gene_rna_effect_summary": results_dir / "all_gene_rna_effect_summary.tsv",
        }
        for artifact_key, artifact_path in optional_artifacts.items():
            if artifact_path.exists():
                result[artifact_key] = str(artifact_path)
        update_job(
            db,
            job_id,
            status="complete",
            stage="complete",
            message="Job complete",
            result=result,
            progress_percent=100,
        )
    except Exception as exc:  # noqa: BLE001
        error_path = root / "logs" / "error.txt"
        write_text(error_path, f"{type(exc).__name__}: {exc}\n")
        update_job(
            db,
            job_id,
            status="failed",
            stage="failed",
            message=f"{type(exc).__name__}: {exc}",
            progress_percent=100,
        )
