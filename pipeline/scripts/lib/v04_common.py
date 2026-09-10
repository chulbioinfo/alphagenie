#!/usr/bin/env python3
"""Shared helpers for the v0.4 RNA calibration workflow."""

from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd


BRAIN_GROUP_ORDER = [
    "Whole brain",
    "Cortex / frontal cortex",
    "Hippocampus",
    "Basal ganglia",
    "Cerebellum",
    "Other brain",
    "Developmental brain / neural progenitor",
    "Neural / glial cells",
]

VARIANT_ORDER = [
    "AUTS2_del6",
    "MSANTD3_del6",
    "ZZZ3_del3",
    "HOXC8_del3",
    "RBFOX1_del3",
    "TRAF3IP1_del3",
    "RNPEPL1_del3",
    "RBPJ_del3",
    "ZNF704_del3",
    "ERVK13-1_mnv",
    "SPSB4_snv",
    "CNTFR_snv",
]


def safe_stem(value: str) -> str:
    chars = [c if (c.isalnum() or c in {"-", "_", "."}) else "_" for c in str(value)]
    return "".join(chars).strip("_") or "value"


def infer_variant_class(ref: str, alt: str) -> str:
    ref = str(ref).upper()
    alt = str(alt).upper()
    if len(ref) == len(alt) == 1:
        return "snv"
    if len(ref) == len(alt):
        return f"mnv_{len(ref)}bp"
    if len(ref) > len(alt):
        return f"deletion_{len(ref) - len(alt)}bp"
    return f"insertion_{len(alt) - len(ref)}bp"


def add_variant_id_columns(variants: pd.DataFrame) -> pd.DataFrame:
    variants = variants.copy()
    if "variant_class" not in variants.columns:
        variants["variant_class"] = [
            infer_variant_class(r, a) for r, a in zip(variants["ref"], variants["alt"], strict=False)
        ]
    else:
        missing = variants["variant_class"].isna() | variants["variant_class"].astype(str).str.strip().eq("")
        variants.loc[missing, "variant_class"] = [
            infer_variant_class(r, a)
            for r, a in zip(variants.loc[missing, "ref"], variants.loc[missing, "alt"], strict=False)
        ]
    if "representation" not in variants.columns:
        variants["representation"] = "input"
    if "sub_index" not in variants.columns:
        variants["sub_index"] = variants.groupby("variant_group_id").cumcount().astype(str)
    variants["variant_id"] = (
        variants["variant_group_id"].astype(str)
        + "|"
        + variants["representation"].astype(str)
        + "|"
        + variants["sub_index"].astype(str)
    )
    return variants


def read_variants(path: Path) -> pd.DataFrame:
    required = {"variant_group_id", "gene_symbol", "chrom", "pos1", "ref", "alt"}
    variants = pd.read_csv(path, sep="\t", dtype=str)
    missing = sorted(required - set(variants.columns))
    if missing:
        raise SystemExit(f"[ERROR] {path} missing columns: {', '.join(missing)}")
    return add_variant_id_columns(variants)


def is_deletion_class(value: object) -> bool:
    return str(value).lower().startswith("deletion")


def is_substitution_class(value: object) -> bool:
    text = str(value).lower()
    return text.startswith("snv") or text.startswith("mnv") or text.startswith("substitution")


def classify_brain_group(row: pd.Series) -> tuple[str, str]:
    fields = [
        row.get("biosample_name", ""),
        row.get("biosample_type", ""),
        row.get("biosample_life_stage", ""),
        row.get("gtex_tissue", ""),
        row.get("ontology_curie", ""),
        row.get("track_name", ""),
    ]
    text = " ".join(str(x) for x in fields).lower().replace("_", " ")
    ontology = str(row.get("ontology_curie", "")).upper()
    if re.search(r"kidney|renal|nephron|adrenal", text):
        if str(row.get("biosample_type", "")).lower() == "cell_line":
            return "Non-brain cell line", "nonbrain_control"
        if str(row.get("biosample_type", "")).lower() == "primary_cell":
            return "Primary non-brain cell", "nonbrain_control"
        return "Non-brain tissue / other", "nonbrain_control"
    if re.search(r"neural progenitor|neuronal stem|neurosphere|fetal brain|embryonic brain", text):
        return "Developmental brain / neural progenitor", "brain_primary"
    if re.search(r"basal ganglia|caudate|putamen|nucleus accumbens|striatum", text):
        return "Basal ganglia", "brain_primary"
    if re.search(r"cortex|frontal", text):
        return "Cortex / frontal cortex", "brain_primary"
    if "cerebell" in text:
        return "Cerebellum", "brain_primary"
    if "hippoc" in text:
        return "Hippocampus", "brain_primary"
    if "whole brain" in text or ontology == "UBERON:0000955":
        return "Whole brain", "brain_primary"
    if re.search(
        r"amygdala|diencephalon|hypothalamus|substantia nigra|occipital lobe|parietal lobe|"
        r"temporal lobe|spinal cord|cervical spinal cord|forebrain|midbrain|hindbrain|telencephalon|"
        r"cerebral hemisphere|cerebrum",
        text,
    ):
        return "Other brain", "brain_primary"
    if "brain" in text:
        return "Other brain", "brain_primary"
    if re.search(r"neuron|purkinje|astrocyte|oligodendro|microglia|neural|glia", text):
        return "Neural / glial cells", "brain_primary"
    if str(row.get("biosample_type", "")).lower() == "cell_line":
        return "Non-brain cell line", "nonbrain_control"
    if str(row.get("biosample_type", "")).lower() == "primary_cell":
        return "Primary non-brain cell", "nonbrain_control"
    if str(row.get("biosample_type", "")).lower() == "in_vitro_differentiated_cells":
        return "In vitro non-neural", "nonbrain_control"
    return "Non-brain tissue / other", "nonbrain_control"


def prepare_target_rows(scores: pd.DataFrame, variants: pd.DataFrame) -> pd.DataFrame:
    output_type = scores["output_type"].astype(str) if "output_type" in scores.columns else pd.Series("", index=scores.index)
    scorer = scores["variant_scorer"].astype(str) if "variant_scorer" in scores.columns else pd.Series("", index=scores.index)
    rna = scores[output_type.eq("RNA_SEQ") & scorer.str.startswith("GeneMaskLFCScorer")].copy()
    if rna.empty:
        raise SystemExit("[ERROR] no RNA_SEQ GeneMaskLFCScorer rows found")
    if "variant_group_id" not in rna.columns:
        rna["variant_group_id"] = rna["variant_id"].astype(str).str.split("|").str[0]
    rna = rna.drop(columns=[c for c in ["gene_symbol_variant", "variant_class_variant"] if c in rna.columns])
    meta = variants.drop_duplicates("variant_group_id")[
        ["variant_group_id", "gene_symbol", "variant_class"]
    ]
    rna = rna.merge(meta, on="variant_group_id", how="left", suffixes=("", "_variant"))
    if "gene_symbol" not in rna.columns:
        rna["gene_symbol"] = rna["gene_symbol_variant"]
    else:
        rna["gene_symbol"] = rna["gene_symbol"].fillna(rna.get("gene_symbol_variant"))
    if "variant_class" not in rna.columns:
        rna["variant_class"] = rna["variant_class_variant"]
    else:
        rna["variant_class"] = rna["variant_class"].fillna(rna.get("variant_class_variant"))
    if "gene_name" not in rna.columns:
        rna["gene_name"] = rna["gene_symbol"]
    rna = rna[rna["gene_name"].astype(str).str.upper().eq(rna["gene_symbol"].astype(str).str.upper())].copy()
    if "raw_score" not in rna.columns:
        raise SystemExit("[ERROR] RNA score table missing raw_score")
    if "quantile_score" not in rna.columns:
        rna["quantile_score"] = np.nan
    rna["raw_delta_rna"] = pd.to_numeric(rna["raw_score"], errors="coerce")
    rna["quantile_abs"] = pd.to_numeric(rna["quantile_score"], errors="coerce").abs()
    groups = rna.apply(classify_brain_group, axis=1, result_type="expand")
    rna["brain_group"] = groups[0]
    rna["track_scope"] = groups[1]
    rna["track_key"] = (
        rna.get("track_name", "").astype(str)
        + "||"
        + rna.get("biosample_name", "").astype(str)
        + "||"
        + rna.get("ontology_curie", "").astype(str)
        + "||"
        + rna.get("data_source", "").astype(str)
    )
    return rna


def bh_fdr(p_values: pd.Series) -> pd.Series:
    p = pd.to_numeric(p_values, errors="coerce")
    out = pd.Series(np.nan, index=p.index, dtype=float)
    valid = p.dropna()
    if valid.empty:
        return out
    order = valid.sort_values().index
    ranked = valid.loc[order].to_numpy(dtype=float)
    n = len(ranked)
    adjusted = np.minimum.accumulate((ranked * n / np.arange(1, n + 1))[::-1])[::-1]
    out.loc[order] = np.clip(adjusted, 0, 1)
    return out


def median_mad(values: pd.Series) -> tuple[float, float]:
    vals = pd.to_numeric(values, errors="coerce").dropna().to_numpy(dtype=float)
    if vals.size == 0:
        return math.nan, math.nan
    med = float(np.median(vals))
    mad = float(np.median(np.abs(vals - med)))
    return med, mad


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_tsv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, sep="\t", index=False)
    print(f"[OK] wrote {path} rows={len(df)}")
