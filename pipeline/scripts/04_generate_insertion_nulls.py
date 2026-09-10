#!/usr/bin/env python3
"""Generate fixed-real-interval pseudo-insertions for insertion calibration."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from alphagenome.data import genome

from lib.fasta import FastaExtractor  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--variants", type=Path, required=True)
    p.add_argument("--hg38", type=Path, default=Path("data/external/hg38.fa"))
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--per-group", type=int, default=500)
    p.add_argument("--sequence-length", type=int, default=1_048_576)
    p.add_argument("--seed", type=int, default=20260527)
    return p.parse_args()


def gc_fraction(seq: str) -> float:
    return sum(1 for b in seq.upper() if b in {"G", "C"}) / max(len(seq), 1)


def main() -> int:
    args = parse_args()
    variants = pd.read_csv(args.variants, sep="\t", dtype=str)
    insertions = variants[variants["variant_class"].astype(str).str.startswith("insertion")].drop_duplicates("variant_group_id")
    if insertions.empty:
        raise SystemExit("[ERROR] no insertion rows found")
    extractor = FastaExtractor(args.hg38)
    rng = np.random.default_rng(args.seed)
    rows: list[dict[str, object]] = []
    for real in insertions.itertuples(index=False):
        real_variant = genome.Variant(
            chromosome=str(real.chrom),
            position=int(real.pos1),
            reference_bases=str(real.ref),
            alternate_bases=str(real.alt),
        )
        interval = real_variant.reference_interval.resize(args.sequence_length)
        seq = extractor.fetch_bed(str(real.chrom), int(interval.start), int(interval.end))
        inserted = str(real.alt)[len(str(real.ref)) :].upper()
        if not inserted:
            raise SystemExit(f"[ERROR] {real.variant_group_id}: empty inserted sequence")
        offsets = np.arange(0, len(seq), dtype=np.int64)
        rng.shuffle(offsets)
        seen: set[tuple[str, int, str, str]] = {
            (str(real.chrom), int(real.pos1), str(real.ref).upper(), str(real.alt).upper())
        }
        added = 0
        print(
            f"[INFO] {real.variant_group_id}: fixed_interval={real.chrom}:{interval.start}-{interval.end} "
            f"target={args.per_group}",
            flush=True,
        )
        for offset in offsets:
            if added >= args.per_group:
                break
            anchor = seq[int(offset)].upper()
            if anchor == "N":
                continue
            pos1 = int(interval.start) + int(offset) + 1
            ref = anchor
            alt = anchor + inserted
            key = (str(real.chrom), pos1, ref, alt)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "null_variant_id": f"fixed_{real.variant_group_id}_same_insert_{added:04d}",
                    "matched_real_variant_id": f"{real.chrom}:{real.pos1}:{real.ref}>{real.alt}",
                    "matched_real_variant_group_id": real.variant_group_id,
                    "gene_symbol": real.gene_symbol,
                    "target_gene": real.gene_symbol,
                    "chrom": real.chrom,
                    "pos_1based": pos1,
                    "ref_normalized": ref,
                    "alt_normalized": alt,
                    "insertion_length": len(inserted),
                    "inserted_sequence": inserted,
                    "sequence_phase": anchor,
                    "tss_distance_bin": "same_fixed_1Mb_interval",
                    "promoter_orientation": "matched_real_promoter_interval",
                    "gc_decile": str(max(0, min(10, int(round(gc_fraction(inserted) * 10))))),
                    "cpg_overlap": "not_assessed_fixed_interval",
                    "mappability_bin": "not_assessed_fixed_interval",
                    "exclusion_flags": "",
                    "matching_status": "matched",
                    "gc_fraction": gc_fraction(inserted),
                    "fixed_interval": f"{real.chrom}:{interval.start}-{interval.end}",
                    "sampling_stage": "same_insert_fixed_interval",
                }
            )
            added += 1
        if added < args.per_group:
            raise SystemExit(f"[ERROR] {real.variant_group_id}: only generated {added}/{args.per_group}")
        print(f"[OK] {real.variant_group_id}: added {added}/{args.per_group}", flush=True)
    out = pd.DataFrame(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, sep="\t", index=False)
    print(f"[OK] wrote {args.out} rows={len(out)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
