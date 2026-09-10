# Matched-null ID compatibility fix

This local correction applies to the v0.23 interface / v0.20 analysis engine. It
does not change inference, null sampling, the Brain9 classification, numerical
score values, or the sealed manuscript assets.

## Cause and correction

All three matched-null generators write `null_variant_id` in their design TSV.
The null scorer intentionally writes the same identifier as `null_id` in score
TSVs. The summary reader previously required `null_id` in the original design,
so a successful scoring run stopped before classification and aggregation.
This failure was independent of the requested null count.

`read_matched_null_ids` accepts the native `null_variant_id` column and the
compatible `null_id` alias. If both exist, they must agree exactly. Empty,
blank, duplicate, and conflicting IDs are rejected. Identifiers remain strings;
the original sampled design is copied byte-for-byte, not rewritten. Existing
checks still require exact design/scored ID membership, the requested null
count, complete track coverage, finite scores, and unchanged classification
metadata. Ten-null smoke tests and 1,000-null analyses use the same ID contract.

The combined cohort null table is now registered for local downloads only when
every child has its null export. Combining preserves string IDs, and a stale or
partial table is not advertised as a current export. Failed-child cohorts still
withhold cohort statistics.

## Offline verification

Run these from the repository in its dedicated virtual environment. Tests use
synthetic credentials and temporary state; do not source a credential script.

```sh
.venv/bin/python -m unittest discover -s tests -p test_null_source_exports.py -v
.venv/bin/python -m unittest discover -s tests -p test_multi_null_exports.py -v
.venv/bin/python -m unittest discover -s tests -p test_brain9_adapter.py -v
```

Coverage includes deletion/insertion/substitution designs; native, alias, and
equal dual-column IDs; leading-zero identifiers; invalid/mismatched IDs and
depths; missing/nonfinite track scores; exact original source preservation;
1,000-null statistics; complete cohort export registration; and no partial or
stale cohort exports. Classification regression also verifies the sealed
v0.20 reference results.

## Existing failed jobs

A server restart loads the correction but does not rewrite historical failed
jobs, resubmit analyses, or make provider requests. Existing score files remain
available for controlled offline re-summarization with `compute_from_scores`.
Use a separate output directory to preserve the original job and its audit
trail. Rendering these score-only outputs does not generate a missing cortex
curve. A fresh cortex prediction requires a separate provider request; do not
claim that an unavailable curve has been generated.

Do not use `run_job` or `run_api_full` as an API-free recovery command: the normal
workflow includes scoring and cortex prediction. Re-submitting in the browser
starts a new analysis and can consume provider quota.
