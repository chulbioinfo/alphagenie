#!/usr/bin/env python3
"""Generate pseudo-deletions inside each real variant's fixed 1 Mb interval."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from alphagenome.data import genome

from lib.fasta import FastaExtractor  # noqa: E402
from lib.variant_utils import VcfVariant  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--variants", type=Path, default=Path("data/input/variants.tsv"))
    p.add_argument("--hg38", type=Path, default=Path("data/external/hg38.fa"))
    p.add_argument("--out", type=Path, default=Path("data/external/pseudo_deletions_fixed_interval.tsv"))
    p.add_argument("--per-group", type=int, default=500)
    p.add_argument("--sequence-length", type=int, default=1_048_576)
    p.add_argument("--seed", type=int, default=20260527)
    return p.parse_args()


def gc_fraction(seq: str) -> float:
    return sum(1 for b in seq.upper() if b in {"G", "C"}) / max(len(seq), 1)


def iter_candidates(seq: str, start0: int, deletion_length: int, rng: np.random.Generator):
    # anchor_pos1 + deletion_length must remain inside the fixed interval.
    max_offset = len(seq) - deletion_length - 1
    offsets = np.arange(0, max_offset, dtype=np.int64)
    rng.shuffle(offsets)
    for offset in offsets:
        anchor = seq[offset]
        deleted = seq[offset + 1 : offset + 1 + deletion_length]
        if "N" in (anchor + deleted).upper():
            continue
        yield start0 + int(offset) + 1, anchor.upper(), deleted.upper()


def left_normalize_in_interval(
    chrom: str,
    pos1: int,
    ref: str,
    alt: str,
    seq: str,
    interval_start0: int,
    max_shift: int = 100,
) -> VcfVariant:
    pos = int(pos1)
    ref_s = str(ref).upper()
    alt_s = str(alt).upper()
    while len(ref_s) > 1 and len(alt_s) > 1 and ref_s[-1] == alt_s[-1]:
        ref_s = ref_s[:-1]
        alt_s = alt_s[:-1]
    shifted = 0
    while ref_s and alt_s and ref_s[0] == alt_s[0]:
        if pos <= interval_start0 + 1 or shifted >= max_shift:
            break
        prev_offset = pos - 2 - interval_start0
        if prev_offset < 0 or prev_offset >= len(seq):
            break
        prev = seq[prev_offset].upper()
        ref_s = prev + ref_s
        alt_s = prev + alt_s
        pos -= 1
        shifted += 1
        while len(ref_s) > 1 and len(alt_s) > 1 and ref_s[-1] == alt_s[-1]:
            ref_s = ref_s[:-1]
            alt_s = alt_s[:-1]
    while len(ref_s) > 1 and len(alt_s) > 1 and ref_s[0] == alt_s[0]:
        ref_s = ref_s[1:]
        alt_s = alt_s[1:]
        pos += 1
    return VcfVariant(chrom=chrom, pos1=pos, ref=ref_s, alt=alt_s)


def main() -> int:
    args = parse_args()
    variants = pd.read_csv(args.variants, sep="\t", dtype=str)
    deletions = variants[variants["variant_class"].astype(str).str.startswith("deletion")].drop_duplicates("variant_group_id")
    extractor = FastaExtractor(args.hg38)
    rng = np.random.default_rng(args.seed)
    rows: list[dict[str, object]] = []
    stages = [
        ("same_CG_gc10", True, 0.10),
        ("same_CG_gc20", True, 0.20),
        ("gc20_no_CG_requirement", False, 0.20),
        ("length_only_fixed_interval", False, 1.00),
    ]
    for real in deletions.itertuples(index=False):
        real_variant = genome.Variant(
            chromosome=str(real.chrom),
            position=int(real.pos1),
            reference_bases=str(real.ref),
            alternate_bases=str(real.alt),
        )
        interval = real_variant.reference_interval.resize(args.sequence_length)
        seq = extractor.fetch_bed(str(real.chrom), int(interval.start), int(interval.end))
        deletion_length = len(str(real.ref)) - len(str(real.alt))
        real_gc = gc_fraction(str(real.ref)[1:])
        seen: set[tuple[str, int, str, str]] = set()
        real_key = (str(real.chrom), int(real.pos1), str(real.ref), str(real.alt))
        seen.add(real_key)
        added = 0
        print(
            f"[INFO] {real.variant_group_id}: fixed_interval={real.chrom}:{interval.start}-{interval.end} "
            f"target={args.per_group}",
            flush=True,
        )
        for stage, require_cg, gc_tol in stages:
            if added >= args.per_group:
                break
            for anchor_pos1, anchor, deleted in iter_candidates(seq, int(interval.start), deletion_length, rng):
                if added >= args.per_group:
                    break
                if require_cg and "CG" not in deleted:
                    continue
                gc = gc_fraction(deleted)
                if abs(gc - real_gc) > gc_tol:
                    continue
                cand = VcfVariant(
                    chrom=str(real.chrom),
                    pos1=anchor_pos1,
                    ref=anchor + deleted,
                    alt=anchor,
                )
                norm = left_normalize_in_interval(cand.chrom, cand.pos1, cand.ref, cand.alt, seq, int(interval.start))
                key = (norm.chrom, norm.pos1, norm.ref, norm.alt)
                if key in seen:
                    continue
                if norm.pos1 < interval.start + 1 or norm.pos1 + len(norm.ref) - 1 > interval.end:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "null_variant_id": f"fixed_{real.variant_group_id}_{stage}_{added:04d}",
                        "matched_real_variant_id": f"{real.chrom}:{real.pos1}:{real.ref}>{real.alt}",
                        "matched_real_variant_group_id": real.variant_group_id,
                        "gene_symbol": real.gene_symbol,
                        "target_gene": real.gene_symbol,
                        "chrom": norm.chrom,
                        "pos_1based": norm.pos1,
                        "ref_normalized": norm.ref,
                        "alt_normalized": norm.alt,
                        "deletion_length": deletion_length,
                        "sequence_phase": deleted,
                        "tss_distance_bin": "same_fixed_1Mb_interval",
                        "promoter_orientation": "matched_real_promoter_interval",
                        "gc_decile": str(max(0, min(10, int(round(gc * 10))))),
                        "cpg_overlap": "not_assessed_fixed_interval",
                        "mappability_bin": "not_assessed_fixed_interval",
                        "exclusion_flags": "",
                        "matching_status": "matched",
                        "gc_fraction": gc,
                        "fixed_interval": f"{real.chrom}:{interval.start}-{interval.end}",
                        "sampling_stage": stage,
                    }
                )
                added += 1
            print(f"[OK] {real.variant_group_id}: added {added}/{args.per_group} after {stage}", flush=True)
        if added < args.per_group:
            raise SystemExit(f"[ERROR] {real.variant_group_id}: only generated {added}/{args.per_group}")
    out = pd.DataFrame(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, sep="\t", index=False)
    print(f"[OK] wrote {args.out} rows={len(out)}", flush=True)
    print(out.groupby("matched_real_variant_group_id").size().to_string(), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
