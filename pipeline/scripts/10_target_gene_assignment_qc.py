#!/usr/bin/env python3
"""Target-gene assignment QC for AlphaGenome variant analyses.

This script checks the part of the analysis that should never be implicit:
whether each forward-strand VCF-style variant is consistent with the intended
target gene's GENCODE chromosome, strand, and annotated TSS context.

It also optionally scans real AlphaGenome RNA_SEQ scores to verify that
GeneMaskLFCScorer rows for the intended target gene exist, and to report nearby
genes with larger predicted RNA effects. These neighbor summaries are QC
context, not a substitute for the pre-specified target-gene analysis.
"""

from __future__ import annotations

import argparse
import gzip
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from alphagenome.data import genome

from lib.fasta import FastaExtractor
from lib.v04_common import add_variant_id_columns, read_variants, write_tsv


ATTR_RE = re.compile(r'(\S+) "([^"]*)"')
RNA_COLUMNS = [
    "variant_group_id",
    "variant_id",
    "output_type",
    "variant_scorer",
    "gene_name",
    "raw_score",
]


@dataclass(frozen=True)
class GeneFeature:
    gene_symbol: str
    gene_id: str
    gene_type: str
    chrom: str
    strand: str
    start0: int
    end0: int
    source: str

    @property
    def tss0(self) -> int:
        return self.start0 if self.strand == "+" else self.end0 - 1


@dataclass(frozen=True)
class TssFeature:
    gene_symbol: str
    gene_id: str
    transcript_id: str
    transcript_type: str
    chrom: str
    strand: str
    tss0: int
    start0: int
    end0: int
    source: str
    tags: tuple[str, ...]

    @property
    def is_mane_select(self) -> bool:
        return any(tag == "MANE_Select" for tag in self.tags)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--variants",
        type=Path,
        action="append",
        required=True,
        help="Variant TSV. Pass multiple times for CCG12 plus PTCHD1.",
    )
    p.add_argument("--gtf", type=Path, required=True, help="GENCODE/Ensembl GTF, plain or .gz.")
    p.add_argument("--hg38", type=Path, required=True, help="hg38 FASTA with .fai index.")
    p.add_argument(
        "--score-tsv",
        type=Path,
        action="append",
        default=[],
        help="Optional real AlphaGenome score TSV for target-vs-neighbor gene QC.",
    )
    p.add_argument("--sequence-length", type=int, default=1_048_576)
    p.add_argument("--core-window-bp", type=int, default=250)
    p.add_argument("--promoter-upstream-bp", type=int, default=2_000)
    p.add_argument("--promoter-downstream-bp", type=int, default=500)
    p.add_argument("--chunk-size", type=int, default=250_000)
    p.add_argument("--out", type=Path, default=Path("data/qc/target_gene_assignment_qc.tsv"))
    p.add_argument("--neighbor-out", type=Path, default=Path("results/tables/target_vs_neighbor_gene_effects.tsv"))
    p.add_argument("--all-gene-out", type=Path, default=Path("results/tables/all_gene_rna_effect_summary.tsv"))
    return p.parse_args()


def open_text(path: Path):
    if not path.exists():
        raise SystemExit(f"[ERROR] missing annotation file: {path}")
    if path.suffix == ".gz":
        return gzip.open(path, "rt")
    return path.open("rt")


def parse_attrs(text: str) -> dict[str, object]:
    attrs: dict[str, object] = {}
    tags: list[str] = []
    for match in ATTR_RE.finditer(text):
        key, value = match.groups()
        if key == "tag":
            tags.append(value)
        elif key not in attrs:
            attrs[key] = value
    attrs["tags"] = tags
    return attrs


def read_all_variants(paths: Iterable[Path]) -> pd.DataFrame:
    frames = []
    for path in paths:
        frame = read_variants(path)
        frame["variant_source_file"] = str(path)
        frames.append(frame)
    if not frames:
        raise SystemExit("[ERROR] no variant TSVs provided")
    variants = pd.concat(frames, ignore_index=True)
    variants = add_variant_id_columns(variants)
    variants["pos1"] = pd.to_numeric(variants["pos1"], errors="raise").astype(int)
    variants["ref"] = variants["ref"].astype(str).str.upper()
    variants["alt"] = variants["alt"].astype(str).str.upper()
    return variants


def load_gene_annotation(gtf: Path, wanted_symbols: set[str]) -> tuple[dict[str, list[GeneFeature]], dict[str, list[TssFeature]]]:
    wanted = {s.upper() for s in wanted_symbols}
    gene_features: dict[str, list[GeneFeature]] = {s: [] for s in wanted}
    tss_features: dict[str, list[TssFeature]] = {s: [] for s in wanted}
    with open_text(gtf) as fh:
        for line in fh:
            if not line or line.startswith("#"):
                continue
            fields = line.rstrip("\n").split("\t")
            if len(fields) != 9:
                continue
            chrom, source, feature, start1, end1, _score, strand, _phase, attr_text = fields
            if feature not in {"gene", "transcript"}:
                continue
            attrs = parse_attrs(attr_text)
            gene_name = str(attrs.get("gene_name", ""))
            key = gene_name.upper()
            if key not in wanted:
                continue
            start0 = int(start1) - 1
            end0 = int(end1)
            gene_id = str(attrs.get("gene_id", ""))
            if feature == "gene":
                gene_features[key].append(
                    GeneFeature(
                        gene_symbol=gene_name,
                        gene_id=gene_id,
                        gene_type=str(attrs.get("gene_type", attrs.get("gene_biotype", ""))),
                        chrom=chrom,
                        strand=strand,
                        start0=start0,
                        end0=end0,
                        source=source,
                    )
                )
            else:
                transcript_id = str(attrs.get("transcript_id", ""))
                tss0 = start0 if strand == "+" else end0 - 1
                tss_features[key].append(
                    TssFeature(
                        gene_symbol=gene_name,
                        gene_id=gene_id,
                        transcript_id=transcript_id,
                        transcript_type=str(attrs.get("transcript_type", attrs.get("transcript_biotype", ""))),
                        chrom=chrom,
                        strand=strand,
                        tss0=tss0,
                        start0=start0,
                        end0=end0,
                        source=source,
                        tags=tuple(str(x) for x in attrs.get("tags", [])),
                    )
                )
    return gene_features, tss_features


def signed_distance(edit_center0: float, tss0: int, strand: str) -> float:
    if strand == "+":
        return edit_center0 - tss0
    if strand == "-":
        return tss0 - edit_center0
    return math.nan


def edit_interval(row: pd.Series) -> tuple[float, float, float, str]:
    """Return edit_start0, edit_end0, edit_center0, edit_model.

    For VCF-style indels, the shared anchor base is not treated as the edited
    sequence. Insertions are represented as a point immediately after the anchor.
    """
    pos1 = int(row["pos1"])
    ref = str(row["ref"]).upper()
    alt = str(row["alt"]).upper()
    pos0 = pos1 - 1
    if len(ref) == len(alt):
        start0 = float(pos0)
        end0 = float(pos0 + len(ref))
        model = "substitution_interval"
    elif len(ref) > len(alt) and ref.startswith(alt):
        start0 = float(pos0 + len(alt))
        end0 = float(pos0 + len(ref))
        model = "anchored_deletion_without_anchor"
    elif len(alt) > len(ref) and alt.startswith(ref):
        start0 = float(pos0 + len(ref))
        end0 = start0
        model = "anchored_insertion_after_anchor"
    else:
        start0 = float(pos0)
        end0 = float(pos0 + len(ref))
        model = "complex_vcf_ref_interval"
    center0 = start0 if end0 == start0 else (start0 + end0) / 2.0
    return start0, end0, center0, model


def ref_check(extractor: FastaExtractor, row: pd.Series) -> tuple[str, str]:
    chrom = str(row["chrom"])
    pos1 = int(row["pos1"])
    ref = str(row["ref"]).upper()
    try:
        observed = extractor.fetch(chrom, pos1, pos1 + len(ref) - 1)
    except Exception as exc:  # noqa: BLE001
        return "ERROR_REF_FETCH_FAILED", str(exc)
    if observed == ref:
        return "PASS_REF_MATCH", observed
    return "FAIL_REF_MISMATCH", observed


def score_interval(row: pd.Series, sequence_length: int) -> tuple[int, int]:
    variant = genome.Variant(
        chromosome=str(row["chrom"]),
        position=int(row["pos1"]),
        reference_bases=str(row["ref"]).upper(),
        alternate_bases=str(row["alt"]).upper(),
    )
    interval = variant.reference_interval.resize(sequence_length)
    return int(interval.start), int(interval.end)


def choose_tss(
    row: pd.Series,
    gene_features: list[GeneFeature],
    tss_features: list[TssFeature],
    edit_center0: float,
) -> dict[str, object]:
    chrom = str(row["chrom"])
    transcript_same_chrom = [t for t in tss_features if t.chrom == chrom]
    mane_same_chrom = [t for t in transcript_same_chrom if t.is_mane_select]
    candidates: list[TssFeature | GeneFeature]
    source_label: str
    if mane_same_chrom:
        candidates = mane_same_chrom
        source_label = "MANE_Select_transcript"
    elif transcript_same_chrom:
        candidates = transcript_same_chrom
        source_label = "nearest_GENCODE_transcript"
    else:
        gene_same_chrom = [g for g in gene_features if g.chrom == chrom]
        candidates = gene_same_chrom
        source_label = "gene_feature_fallback"

    if not candidates:
        return {
            "selected_tss_source": "",
            "selected_transcript_id": "",
            "selected_gene_id": "",
            "selected_gene_type": "",
            "selected_transcript_type": "",
            "gene_chrom": "",
            "gene_strand": "",
            "gene_start0": np.nan,
            "gene_end0": np.nan,
            "selected_tss0": np.nan,
            "signed_distance_to_selected_tss_bp": np.nan,
            "abs_distance_to_selected_tss_bp": np.nan,
            "n_gencode_transcripts_same_chrom": 0,
            "n_mane_select_transcripts_same_chrom": 0,
            "nearest_any_transcript_tss0": np.nan,
            "nearest_any_transcript_signed_distance_bp": np.nan,
            "nearest_any_transcript_id": "",
        }

    def abs_dist(candidate: TssFeature | GeneFeature) -> float:
        return abs(signed_distance(edit_center0, candidate.tss0, candidate.strand))

    selected = min(candidates, key=abs_dist)
    nearest_any = min(transcript_same_chrom, key=abs_dist) if transcript_same_chrom else None
    gene_same_chrom = [g for g in gene_features if g.chrom == chrom]
    gene_record = gene_same_chrom[0] if gene_same_chrom else None

    selected_transcript_id = selected.transcript_id if isinstance(selected, TssFeature) else ""
    selected_transcript_type = selected.transcript_type if isinstance(selected, TssFeature) else ""
    selected_gene_type = gene_record.gene_type if gene_record else getattr(selected, "gene_type", "")
    selected_signed = signed_distance(edit_center0, selected.tss0, selected.strand)
    nearest_any_signed = (
        signed_distance(edit_center0, nearest_any.tss0, nearest_any.strand)
        if nearest_any is not None
        else np.nan
    )
    return {
        "selected_tss_source": source_label,
        "selected_transcript_id": selected_transcript_id,
        "selected_gene_id": selected.gene_id,
        "selected_gene_type": selected_gene_type,
        "selected_transcript_type": selected_transcript_type,
        "gene_chrom": selected.chrom,
        "gene_strand": selected.strand,
        "gene_start0": gene_record.start0 if gene_record else selected.start0,
        "gene_end0": gene_record.end0 if gene_record else selected.end0,
        "selected_tss0": selected.tss0,
        "signed_distance_to_selected_tss_bp": selected_signed,
        "abs_distance_to_selected_tss_bp": abs(selected_signed),
        "n_gencode_transcripts_same_chrom": len(transcript_same_chrom),
        "n_mane_select_transcripts_same_chrom": len(mane_same_chrom),
        "nearest_any_transcript_tss0": nearest_any.tss0 if nearest_any is not None else np.nan,
        "nearest_any_transcript_signed_distance_bp": nearest_any_signed,
        "nearest_any_transcript_id": nearest_any.transcript_id if nearest_any is not None else "",
    }


def annotation_status(record: dict[str, object], args: argparse.Namespace) -> str:
    if record["hg38_ref_status"] != "PASS_REF_MATCH":
        return str(record["hg38_ref_status"])
    if not record["gene_annotation_found"]:
        return "FAIL_GENE_SYMBOL_NOT_FOUND_IN_GTF"
    if not record["target_gene_on_variant_chrom"]:
        return "FAIL_TARGET_GENE_CHROMOSOME_MISMATCH"
    if not record["selected_tss_in_alphagenome_interval"]:
        return "FAIL_SELECTED_TSS_OUTSIDE_ALPHAGENOME_INTERVAL"
    dist = float(record["signed_distance_to_selected_tss_bp"])
    if abs(dist) <= args.core_window_bp:
        return "PASS_CORE_TSS_WINDOW"
    if -args.promoter_upstream_bp <= dist <= args.promoter_downstream_bp:
        return "PASS_PROXIMAL_PROMOTER_WINDOW"
    any_dist = record.get("nearest_any_transcript_signed_distance_bp", np.nan)
    if pd.notna(any_dist) and abs(float(any_dist)) <= args.core_window_bp:
        return "WARN_PASS_CORE_ONLY_NON_SELECTED_TSS"
    if pd.notna(any_dist) and -args.promoter_upstream_bp <= float(any_dist) <= args.promoter_downstream_bp:
        return "WARN_PASS_PROXIMAL_ONLY_NON_SELECTED_TSS"
    return "WARN_DISTAL_TO_ANNOTATED_TSS"


def build_assignment_qc(args: argparse.Namespace, variants: pd.DataFrame) -> pd.DataFrame:
    wanted_symbols = set(variants["gene_symbol"].astype(str))
    print(f"[INFO] loading GTF records for {len(wanted_symbols)} target genes from {args.gtf}", flush=True)
    genes, tsses = load_gene_annotation(args.gtf, wanted_symbols)
    extractor = FastaExtractor(args.hg38)
    records: list[dict[str, object]] = []
    for row in variants.to_dict("records"):
        s = pd.Series(row)
        gene_key = str(s["gene_symbol"]).upper()
        start0, end0, center0, edit_model = edit_interval(s)
        interval_start0, interval_end0 = score_interval(s, args.sequence_length)
        ref_status, observed_ref = ref_check(extractor, s)
        gene_features = genes.get(gene_key, [])
        tss_features = tsses.get(gene_key, [])
        selected = choose_tss(s, gene_features, tss_features, center0)
        target_on_chrom = bool(gene_features or tss_features) and bool(
            selected.get("gene_chrom") == str(s["chrom"])
        )
        selected_tss = selected.get("selected_tss0", np.nan)
        tss_in_interval = bool(
            pd.notna(selected_tss)
            and int(interval_start0) <= int(selected_tss) < int(interval_end0)
        )
        gene_found = bool(gene_features or tss_features)
        rec = {
            **row,
            "edit_start0": start0,
            "edit_end0": end0,
            "edit_center0": center0,
            "edit_model": edit_model,
            "hg38_ref_status": ref_status,
            "hg38_ref_observed": observed_ref,
            "alphagenome_interval_start0": interval_start0,
            "alphagenome_interval_end0": interval_end0,
            "gene_annotation_found": gene_found,
            "target_gene_on_variant_chrom": target_on_chrom,
            **selected,
            "selected_tss_in_alphagenome_interval": tss_in_interval,
            "within_core_tss_window": (
                pd.notna(selected.get("signed_distance_to_selected_tss_bp", np.nan))
                and abs(float(selected["signed_distance_to_selected_tss_bp"])) <= args.core_window_bp
            ),
            "within_proximal_promoter_window": (
                pd.notna(selected.get("signed_distance_to_selected_tss_bp", np.nan))
                and -args.promoter_upstream_bp
                <= float(selected["signed_distance_to_selected_tss_bp"])
                <= args.promoter_downstream_bp
            ),
        }
        rec["target_assignment_status"] = annotation_status(rec, args)
        records.append(rec)
    return pd.DataFrame(records)


def read_real_score_subset(path: Path, chunk_size: int) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        print(f"[WARN] score TSV missing or empty, skipping neighbor QC: {path}", flush=True)
        return pd.DataFrame()
    header = pd.read_csv(path, sep="\t", nrows=0)
    missing = sorted(set(RNA_COLUMNS) - set(header.columns))
    if missing:
        print(f"[WARN] score TSV missing columns {missing}; skipping neighbor QC for {path}", flush=True)
        return pd.DataFrame()
    frames = []
    for chunk in pd.read_csv(path, sep="\t", usecols=RNA_COLUMNS, chunksize=chunk_size):
        scorer = chunk["variant_scorer"].astype(str)
        sub = chunk[
            chunk["output_type"].astype(str).eq("RNA_SEQ")
            & scorer.str.startswith("GeneMaskLFCScorer")
        ].copy()
        if sub.empty:
            continue
        sub["raw_score"] = pd.to_numeric(sub["raw_score"], errors="coerce")
        sub = sub.dropna(subset=["raw_score"])
        frames.append(sub[["variant_group_id", "variant_id", "gene_name", "raw_score"]])
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out["score_source_file"] = str(path)
    return out


def summarize_neighbor_effects(
    score_paths: list[Path],
    variants: pd.DataFrame,
    chunk_size: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    frames = [read_real_score_subset(path, chunk_size) for path in score_paths]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame(), pd.DataFrame()
    scores = pd.concat(frames, ignore_index=True)
    expected_groups = set(variants["variant_group_id"].astype(str))
    scores = scores[scores["variant_group_id"].astype(str).isin(expected_groups)].copy()
    if scores.empty:
        return pd.DataFrame(), pd.DataFrame()
    grouped = (
        scores.groupby(["variant_group_id", "gene_name"], dropna=False)
        .agg(
            n_rna_tracks=("raw_score", "size"),
            median_raw_delta=("raw_score", "median"),
            median_abs_raw_delta=("raw_score", lambda x: float(np.median(np.abs(pd.to_numeric(x, errors="coerce").dropna())))),
            max_abs_raw_delta=("raw_score", lambda x: float(np.max(np.abs(pd.to_numeric(x, errors="coerce").dropna())))),
        )
        .reset_index()
    )
    grouped["effect_rank_within_variant"] = (
        grouped.groupby("variant_group_id")["median_abs_raw_delta"]
        .rank(ascending=False, method="min")
        .astype(int)
    )
    target_map = (
        variants.drop_duplicates("variant_group_id")
        .set_index("variant_group_id")["gene_symbol"]
        .astype(str)
        .str.upper()
        .to_dict()
    )
    rows: list[dict[str, object]] = []
    for group_id, sub in grouped.groupby("variant_group_id", sort=False):
        target = target_map.get(str(group_id), "")
        sub = sub.sort_values(["median_abs_raw_delta", "max_abs_raw_delta"], ascending=False)
        top = sub.iloc[0]
        target_rows = sub[sub["gene_name"].astype(str).str.upper().eq(target)]
        if target_rows.empty:
            rows.append(
                {
                    "variant_group_id": group_id,
                    "target_gene": target,
                    "alpha_target_score_status": "FAIL_TARGET_GENE_SCORE_ABSENT",
                    "target_gene_effect_rank": np.nan,
                    "target_median_abs_raw_delta": np.nan,
                    "target_median_raw_delta": np.nan,
                    "top_gene_name": top["gene_name"],
                    "top_gene_median_abs_raw_delta": top["median_abs_raw_delta"],
                    "target_to_top_median_abs_ratio": np.nan,
                }
            )
            continue
        target_row = target_rows.sort_values("median_abs_raw_delta", ascending=False).iloc[0]
        ratio = (
            float(target_row["median_abs_raw_delta"]) / float(top["median_abs_raw_delta"])
            if float(top["median_abs_raw_delta"]) > 0
            else np.nan
        )
        if int(target_row["effect_rank_within_variant"]) == 1:
            status = "PASS_TARGET_TOP_ABS_EFFECT"
        elif pd.notna(ratio) and ratio >= 0.5:
            status = "WARN_TARGET_NOT_TOP_BUT_COMPARABLE"
        else:
            status = "WARN_TARGET_NOT_DOMINANT_AG_EFFECT"
        rows.append(
            {
                "variant_group_id": group_id,
                "target_gene": target,
                "alpha_target_score_status": status,
                "target_gene_effect_rank": int(target_row["effect_rank_within_variant"]),
                "target_median_abs_raw_delta": float(target_row["median_abs_raw_delta"]),
                "target_median_raw_delta": float(target_row["median_raw_delta"]),
                "top_gene_name": top["gene_name"],
                "top_gene_median_abs_raw_delta": float(top["median_abs_raw_delta"]),
                "target_to_top_median_abs_ratio": ratio,
            }
        )
    return pd.DataFrame(rows), grouped


def combine_overall_status(qc: pd.DataFrame) -> pd.Series:
    def classify(row: pd.Series) -> str:
        assignment = str(row.get("target_assignment_status", ""))
        alpha = str(row.get("alpha_target_score_status", "NOT_ASSESSED_ALPHA_SCORE_MISSING"))
        if assignment.startswith("FAIL") or assignment.startswith("ERROR"):
            return "FAIL"
        if alpha.startswith("FAIL"):
            return "FAIL"
        if assignment.startswith("WARN") or alpha.startswith("WARN"):
            return "WARN"
        if alpha == "NOT_ASSESSED_ALPHA_SCORE_MISSING":
            return "WARN"
        if assignment.startswith("PASS") and alpha.startswith("PASS"):
            return "PASS"
        return "WARN"

    return qc.apply(classify, axis=1)


def main() -> int:
    args = parse_args()
    variants = read_all_variants(args.variants)
    qc = build_assignment_qc(args, variants)
    neighbor, all_gene = summarize_neighbor_effects(args.score_tsv, variants, args.chunk_size)
    if not neighbor.empty:
        qc = qc.merge(neighbor, on="variant_group_id", how="left")
    else:
        qc["alpha_target_score_status"] = "NOT_ASSESSED_ALPHA_SCORE_MISSING"
    qc["overall_target_qc_status"] = combine_overall_status(qc)
    write_tsv(qc, args.out)
    if not neighbor.empty:
        write_tsv(neighbor, args.neighbor_out)
    if not all_gene.empty:
        write_tsv(all_gene, args.all_gene_out)

    status_counts = qc["overall_target_qc_status"].value_counts(dropna=False).to_dict()
    print(f"[OK] target-gene assignment QC status counts: {status_counts}", flush=True)
    if qc["overall_target_qc_status"].eq("FAIL").any():
        failed = qc.loc[
            qc["overall_target_qc_status"].eq("FAIL"),
            ["variant_group_id", "gene_symbol", "target_assignment_status", "alpha_target_score_status"],
        ]
        print("[ERROR] target-gene QC failures detected:", flush=True)
        print(failed.to_string(index=False), flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
