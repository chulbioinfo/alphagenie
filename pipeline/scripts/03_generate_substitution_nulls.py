#!/usr/bin/env python3
"""Generate fixed-real-interval pseudo-SNV/MNV records for consensus tests."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from alphagenome.data import genome

from lib.fasta import FastaExtractor  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--variants", type=Path, default=Path("data/input/variants.tsv"))
    p.add_argument("--hg38", type=Path, default=Path("data/external/hg38.fa"))
    p.add_argument("--out", type=Path, default=Path("data/external/substitution_fixed_interval_nulls.tsv"))
    p.add_argument("--per-group", type=int, default=500)
    p.add_argument("--sequence-length", type=int, default=1_048_576)
    p.add_argument("--seed", type=int, default=20260527)
    return p.parse_args()


def choose_primary_substitutions(variants: pd.DataFrame) -> pd.DataFrame:
    sub = variants[variants["variant_class"].astype(str).str.startswith("substitution")].copy()
    rows = []
    for _, group in sub.groupby("variant_group_id", sort=False):
        joint = group[group["representation"].astype(str).eq("joint_mnv")]
        rows.append((joint if not joint.empty else group).iloc[0])
    return pd.DataFrame(rows)


def gc_fraction(seq: str) -> float:
    return sum(1 for b in seq.upper() if b in {"G", "C"}) / max(len(seq), 1)


def main() -> int:
    args = parse_args()
    variants = pd.read_csv(args.variants, sep="\t", dtype=str)
    substitutions = choose_primary_substitutions(variants)
    extractor = FastaExtractor(args.hg38)
    rng = np.random.default_rng(args.seed)
    rows: list[dict[str, object]] = []
    for real in substitutions.itertuples(index=False):
        ref = str(real.ref).upper()
        alt = str(real.alt).upper()
        if len(ref) != len(alt):
            raise SystemExit(f"[ERROR] {real.variant_group_id}: not a substitution/MNV")
        diff_offsets = [i for i, (r, a) in enumerate(zip(ref, alt, strict=False)) if r != a]
        real_variant = genome.Variant(
            chromosome=str(real.chrom),
            position=int(real.pos1),
            reference_bases=ref,
            alternate_bases=alt,
        )
        interval = real_variant.reference_interval.resize(args.sequence_length)
        seq = extractor.fetch_bed(str(real.chrom), int(interval.start), int(interval.end))
        offsets = np.arange(0, len(seq) - len(ref), dtype=np.int64)
        rng.shuffle(offsets)
        seen = {(str(real.chrom), int(real.pos1), ref, alt)}
        added = 0
        print(
            f"[INFO] {real.variant_group_id}: fixed_interval={real.chrom}:{interval.start}-{interval.end} "
            f"target={args.per_group} ref={ref} alt={alt}",
            flush=True,
        )
        stages = [
            ("same_refalt", True),
            ("same_edit_offsets", False),
        ]
        for stage, require_exact_ref in stages:
            if added >= args.per_group:
                break
            for offset in offsets:
                if added >= args.per_group:
                    break
                local_ref = seq[int(offset) : int(offset) + len(ref)].upper()
                if "N" in local_ref:
                    continue
                if require_exact_ref and local_ref != ref:
                    continue
                if any(local_ref[i] != ref[i] for i in diff_offsets):
                    continue
                local_alt_list = list(local_ref)
                for i in diff_offsets:
                    local_alt_list[i] = alt[i]
                local_alt = "".join(local_alt_list)
                if local_alt == local_ref:
                    continue
                pos1 = int(interval.start) + int(offset) + 1
                key = (str(real.chrom), pos1, local_ref, local_alt)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "null_variant_id": f"fixed_{real.variant_group_id}_{stage}_{added:04d}",
                        "matched_real_variant_id": f"{real.chrom}:{real.pos1}:{ref}>{alt}",
                        "matched_real_variant_group_id": real.variant_group_id,
                        "gene_symbol": real.gene_symbol,
                        "target_gene": real.gene_symbol,
                        "chrom": real.chrom,
                        "pos_1based": pos1,
                        "ref_normalized": local_ref,
                        "alt_normalized": local_alt,
                        "substitution_length": len(ref),
                        "edit_offsets": ",".join(map(str, diff_offsets)),
                        "sequence_phase": local_ref,
                        "tss_distance_bin": "same_fixed_1Mb_interval",
                        "promoter_orientation": "matched_real_promoter_interval",
                        "gc_decile": str(max(0, min(10, int(round(gc_fraction(local_ref) * 10))))),
                        "cpg_overlap": "not_assessed_fixed_interval",
                        "mappability_bin": "not_assessed_fixed_interval",
                        "exclusion_flags": "",
                        "matching_status": "matched",
                        "gc_fraction": gc_fraction(local_ref),
                        "fixed_interval": f"{real.chrom}:{interval.start}-{interval.end}",
                        "sampling_stage": f"{stage}_fixed_interval",
                        "representation": real.representation,
                    }
                )
                added += 1
            print(f"[OK] {real.variant_group_id}: added {added}/{args.per_group} after {stage}", flush=True)
        if added < args.per_group:
            raise SystemExit(f"[ERROR] {real.variant_group_id}: only generated {added}/{args.per_group}")
        print(f"[OK] {real.variant_group_id}: added {added}/{args.per_group}", flush=True)
    out = pd.DataFrame(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, sep="\t", index=False)
    print(f"[OK] wrote {args.out} rows={len(out)}", flush=True)
    print(out.groupby("matched_real_variant_group_id").size().to_string(), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
