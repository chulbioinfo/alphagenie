#!/usr/bin/env python3
"""Score real variants with AlphaGenome RNA_SEQ and write a tidy TSV.

This script intentionally reads the AlphaGenome API key only from the
`ALPHA_GENOME_API_KEY` environment variable. Do not hard-code credentials in
this repository.
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import pandas as pd
from alphagenome.data import genome
from alphagenome.models import dna_client, variant_scorers

from lib.v04_common import read_variants
from lib.inference_score_provenance import ScoreProvenance, model_create_kwargs, scoring_identity


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--variants", type=Path, default=Path("data/input/variants.tsv"))
    p.add_argument("--out", type=Path, default=Path("data/raw/CCG12_alphagenome_rna_scores.tsv"))
    p.add_argument("--sequence-length", type=int, default=1_048_576)
    p.add_argument("--retry-max", type=int, default=int(os.environ.get("AG_RETRY_MAX", "6")))
    p.add_argument("--retry-base-seconds", type=float, default=float(os.environ.get("AG_RETRY_BASE_SECONDS", "10")))
    return p.parse_args()


def api_key() -> str:
    key = os.environ.get("ALPHA_GENOME_API_KEY", "").strip()
    if not key:
        raise SystemExit("[ERROR] ALPHA_GENOME_API_KEY is missing")
    return key


def completed_variant_ids(path: Path) -> set[str]:
    if not path.exists() or path.stat().st_size == 0:
        return set()
    return set(pd.read_csv(path, sep="\t", usecols=["variant_id"])["variant_id"].astype(str).dropna())


def main() -> int:
    args = parse_args()
    scorers = [variant_scorers.RECOMMENDED_VARIANT_SCORERS["RNA_SEQ"]]
    identity = scoring_identity()
    client_kwargs = model_create_kwargs(identity, dna_client)
    with ScoreProvenance(
        args.out, identity=identity, inputs={"variants": args.variants},
        sequence_length=args.sequence_length, scorers=scorers, method="score_variant.RNA_SEQ",
    ) as provenance:
        return score_variants(args, scorers, client_kwargs, provenance)


def score_variants(args, scorers, client_kwargs, provenance: ScoreProvenance) -> int:
    variants = read_variants(args.variants)
    requested_ids = set(variants["variant_id"].astype(str))
    done = completed_variant_ids(args.out)
    if done:
        before = len(variants)
        variants = variants[~variants["variant_id"].astype(str).isin(done)].reset_index(drop=True)
        print(f"[RESUME] skipping {before - len(variants)} already-scored real variants", flush=True)
    if variants.empty:
        print(f"[OK] all real variants already scored in {args.out}", flush=True)
        return 0

    key = api_key()
    provenance.start_segment()
    model = dna_client.create(key, **client_kwargs)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    failed: list[str] = []
    for i, row in enumerate(variants.itertuples(index=False), start=1):
        variant = genome.Variant(
            chromosome=str(row.chrom),
            position=int(row.pos1),
            reference_bases=str(row.ref).upper(),
            alternate_bases=str(row.alt).upper(),
            name=str(row.variant_id),
        )
        interval = variant.reference_interval.resize(args.sequence_length)
        tidy = None
        for attempt in range(args.retry_max + 1):
            try:
                raw = model.score_variant(
                    interval=interval,
                    variant=variant,
                    variant_scorers=scorers,
                    organism=dna_client.Organism.HOMO_SAPIENS,
                )
                tidy = variant_scorers.tidy_scores(raw)
                break
            except Exception as exc:  # noqa: BLE001
                if attempt >= args.retry_max:
                    print(f"[FAIL] {row.variant_id}: {exc}", flush=True)
                    failed.append(str(row.variant_id))
                    break
                sleep_s = args.retry_base_seconds * (2**attempt)
                print(f"[RETRY] {row.variant_id}: {exc}; sleeping {sleep_s:.1f}s", flush=True)
                time.sleep(sleep_s)
        if tidy is None:
            continue
        tidy["variant_id"] = str(row.variant_id)
        tidy["variant_group_id"] = str(row.variant_group_id)
        tidy["gene_symbol"] = str(row.gene_symbol)
        tidy["variant_class"] = str(row.variant_class)
        tidy["representation"] = str(row.representation)
        tidy["sub_index"] = str(row.sub_index)
        tidy["chrom"] = str(row.chrom)
        tidy["pos1"] = int(row.pos1)
        tidy["ref"] = str(row.ref).upper()
        tidy["alt"] = str(row.alt).upper()
        mode = "a" if args.out.exists() and args.out.stat().st_size > 0 else "w"
        tidy.to_csv(args.out, sep="\t", index=False, mode=mode, header=(mode == "w"))
        provenance.checkpoint(rows_written=len(tidy), variant_ids=[str(row.variant_id)])
        if i % 5 == 0 or i == len(variants):
            print(f"  scored {i}/{len(variants)} real variants", flush=True)
    if not args.out.exists() or args.out.stat().st_size == 0:
        raise SystemExit("[ERROR] no real variants scored successfully")
    completed = completed_variant_ids(args.out)
    missing = sorted(requested_ids - completed)
    if failed or missing:
        raise SystemExit(
            "[ERROR] real variant scoring incomplete.\n"
            f"  failed_this_run={sorted(set(failed))}\n"
            f"  missing_from_output={missing}"
        )
    print(f"[OK] wrote/appended real RNA scores: {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
