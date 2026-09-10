#!/usr/bin/env python3
"""Score fixed-interval pseudo-deletions with AlphaGenome RNA_SEQ."""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import pandas as pd
from alphagenome.data import genome
from alphagenome.models import dna_client, variant_scorers
from lib.inference_score_provenance import ScoreProvenance, model_create_kwargs, scoring_identity


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--pseudo", type=Path, default=Path("data/external/pseudo_deletions_fixed_interval.tsv"))
    p.add_argument("--variants", type=Path, default=Path("data/input/variants.tsv"))
    p.add_argument("--out", type=Path, default=Path("data/external/fixed_interval_null_scores_RNA_SEQ.tsv"))
    p.add_argument("--sequence-length", type=int, default=1_048_576)
    p.add_argument("--batch-size", type=int, default=int(os.environ.get("AG_NULL_BATCH_SIZE", "25")))
    p.add_argument("--max-workers", type=int, default=int(os.environ.get("AG_MAX_WORKERS", "5")))
    p.add_argument("--retry-max", type=int, default=int(os.environ.get("AG_RETRY_MAX", "6")))
    p.add_argument("--retry-base-seconds", type=float, default=float(os.environ.get("AG_RETRY_BASE_SECONDS", "10")))
    return p.parse_args()


def api_key() -> str:
    key = os.environ.get("ALPHA_GENOME_API_KEY", "").strip()
    if not key:
        raise SystemExit("[ERROR] ALPHA_GENOME_API_KEY missing; source the AlphaGenome env first")
    return key


def make_variant(row) -> genome.Variant:
    return genome.Variant(
        chromosome=str(row.chrom),
        position=int(row.pos_1based),
        reference_bases=str(row.ref_normalized).upper(),
        alternate_bases=str(row.alt_normalized).upper(),
        name=str(row.null_variant_id),
    )


def add_metadata(tidy: pd.DataFrame, row, interval) -> pd.DataFrame:
    tidy = tidy.copy()
    tidy["null_id"] = str(row.null_variant_id)
    tidy["variant_group_id"] = str(row.matched_real_variant_group_id)
    tidy["deletion_length"] = getattr(row, "deletion_length", "")
    tidy["insertion_length"] = getattr(row, "insertion_length", "")
    tidy["indel_length"] = getattr(row, "deletion_length", getattr(row, "insertion_length", ""))
    tidy["gc_fraction"] = getattr(row, "gc_fraction", "")
    tidy["fixed_interval"] = str(interval)
    return tidy


def score_one(model, row, interval, scorers, args) -> pd.DataFrame | None:
    variant = make_variant(row)
    if not interval.contains(variant.reference_interval):
        print(f"[FAIL] {row.null_variant_id}: variant outside fixed interval {interval}", flush=True)
        return None
    for attempt in range(args.retry_max + 1):
        try:
            raw = model.score_variant(
                interval=interval,
                variant=variant,
                variant_scorers=scorers,
                organism=dna_client.Organism.HOMO_SAPIENS,
            )
            return add_metadata(variant_scorers.tidy_scores(raw), row, interval)
        except Exception as exc:  # noqa: BLE001
            if attempt >= args.retry_max:
                print(f"[FAIL] {row.null_variant_id}: {exc}", flush=True)
                return None
            sleep_s = args.retry_base_seconds * (2 ** attempt)
            print(f"[RETRY] {row.null_variant_id}: {exc}; sleeping {sleep_s:.1f}s", flush=True)
            time.sleep(sleep_s)
    return None


def score_batch(model, rows, intervals, scorers, args) -> list[pd.DataFrame | None]:
    variants = [make_variant(row) for row in rows]
    for row, interval, variant in zip(rows, intervals, variants, strict=True):
        if not interval.contains(variant.reference_interval):
            print(f"[FAIL] {row.null_variant_id}: variant outside fixed interval {interval}", flush=True)
            return [None for _ in rows]
    for attempt in range(args.retry_max + 1):
        try:
            raw_results = model.score_variants(
                intervals=intervals,
                variants=variants,
                variant_scorers=scorers,
                organism=dna_client.Organism.HOMO_SAPIENS,
                progress_bar=False,
                max_workers=args.max_workers,
            )
            if len(raw_results) != len(rows):
                raise RuntimeError(f"score_variants returned {len(raw_results)} results for {len(rows)} variants")
            return [
                add_metadata(variant_scorers.tidy_scores(raw), row, interval)
                for raw, row, interval in zip(raw_results, rows, intervals, strict=True)
            ]
        except Exception as exc:  # noqa: BLE001
            if attempt >= args.retry_max:
                print(
                    f"[WARN] batch failed after retries; falling back to single-variant scoring. "
                    f"first={rows[0].null_variant_id} last={rows[-1].null_variant_id}: {exc}",
                    flush=True,
                )
                return [score_one(model, row, interval, scorers, args) for row, interval in zip(rows, intervals, strict=True)]
            sleep_s = args.retry_base_seconds * (2 ** attempt)
            print(
                f"[RETRY] batch first={rows[0].null_variant_id} last={rows[-1].null_variant_id}: "
                f"{exc}; sleeping {sleep_s:.1f}s",
                flush=True,
            )
            time.sleep(sleep_s)
    return [None for _ in rows]


def main() -> int:
    args = parse_args()
    scorers = [variant_scorers.RECOMMENDED_VARIANT_SCORERS["RNA_SEQ"]]
    identity = scoring_identity()
    client_kwargs = model_create_kwargs(identity, dna_client)
    with ScoreProvenance(
        args.out, identity=identity, inputs={"variants": args.variants, "pseudo": args.pseudo},
        sequence_length=args.sequence_length, scorers=scorers, method="score_variants.RNA_SEQ",
    ) as provenance:
        return score_null_variants(args, scorers, client_kwargs, provenance)


def score_null_variants(args, scorers, client_kwargs, provenance: ScoreProvenance) -> int:
    pseudo = pd.read_csv(args.pseudo, sep="\t", dtype=str)
    requested_null_ids = set(pseudo["null_variant_id"].astype(str))
    variants = pd.read_csv(args.variants, sep="\t", dtype=str)
    real_intervals = {}
    requested_groups = set(pseudo["matched_real_variant_group_id"].astype(str))
    for real in variants[
        variants["variant_group_id"].astype(str).isin(requested_groups)
    ].drop_duplicates("variant_group_id").itertuples(index=False):
        real_variant = genome.Variant(
            chromosome=str(real.chrom),
            position=int(real.pos1),
            reference_bases=str(real.ref),
            alternate_bases=str(real.alt),
        )
        real_intervals[str(real.variant_group_id)] = real_variant.reference_interval.resize(args.sequence_length)
    completed: set[str] = set()
    if args.out.exists() and args.out.stat().st_size > 0:
        completed = set(pd.read_csv(args.out, sep="\t", usecols=["null_id"])["null_id"].astype(str).dropna())
    if completed:
        before = len(pseudo)
        pseudo = pseudo[~pseudo["null_variant_id"].astype(str).isin(completed)].reset_index(drop=True)
        print(f"[RESUME] skipping {before - len(pseudo)} already-scored null variants", flush=True)
    if pseudo.empty:
        print(f"[OK] all requested null variants already scored in {args.out}", flush=True)
        return 0

    key = api_key()
    provenance.start_segment()
    model = dna_client.create(key, **client_kwargs)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    n_total = len(pseudo)
    wrote_any = False
    failed: list[str] = []
    rows = list(pseudo.itertuples(index=False))
    for start in range(0, len(rows), args.batch_size):
        batch_rows = rows[start : start + args.batch_size]
        batch_intervals = [real_intervals[str(row.matched_real_variant_group_id)] for row in batch_rows]
        scored = score_batch(model, batch_rows, batch_intervals, scorers, args)
        frames = []
        for row, tidy in zip(batch_rows, scored, strict=True):
            if tidy is None:
                failed.append(str(row.null_variant_id))
                continue
            frames.append(tidy)
        if frames:
            out = pd.concat(frames, ignore_index=True)
            mode = "a" if args.out.exists() and args.out.stat().st_size > 0 else "w"
            out.to_csv(args.out, sep="\t", index=False, mode=mode, header=(mode == "w"))
            provenance.checkpoint(rows_written=len(out), variant_ids=out["null_id"].astype(str))
            wrote_any = True
        scored_n = min(start + len(batch_rows), n_total)
        print(f"  scored {scored_n}/{n_total}", flush=True)
    if not wrote_any:
        raise SystemExit("[ERROR] no fixed-interval nulls scored successfully")
    completed = set(pd.read_csv(args.out, sep="\t", usecols=["null_id"])["null_id"].astype(str).dropna())
    missing = sorted(requested_null_ids - completed)
    if failed or missing:
        raise SystemExit(
            "[ERROR] fixed-interval null scoring incomplete.\n"
            f"  failed_this_run={sorted(set(failed))[:50]}\n"
            f"  n_failed_this_run={len(set(failed))}\n"
            f"  n_missing_from_output={len(missing)}\n"
            f"  first_missing_from_output={missing[:50]}"
        )
    print(f"[OK] appended fixed-interval null scores to {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
