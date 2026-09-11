# Brain9 — local.2 classification contract

Grouping version: `brain9_adult8_embryo_v1_20260909`. Implementation:
`worker/brain9.py`. Applies to both single and multi fresh local analyses.

| Display order | Category | Tracks | Primary Brain9? |
|---|---|---:|---|
| 1 | Cerebral cortex | 4 | Yes, adult |
| 2 | Hippocampal formation | 1 | Yes, adult |
| 3 | Basal ganglia / striatum | 3 | Yes, adult |
| 4 | Amygdala | 1 | Yes, adult |
| 5 | Diencephalic regions | 1 | Yes, adult |
| 6 | Midbrain | 1 | Yes, adult |
| 7 | Cerebellum | 2 | Yes, adult |
| 8 | Whole brain | 1 | Yes, adult |
| 9 | Embryo | 7 | Yes, embryonic brain tissue |
| 10 | Non-brain tissues | 153 | No; all available donor stages |
| 11 | Cells & cell lines | 197 | No; all available donor stages |

Embryo is already the ninth member of Brain9, **not an additional tenth brain
category**. It pools seven individual tracks (four cortex, one diencephalon,
two cerebellum). Track counts are assay counts, not biological replicate counts.
Brain9 is the median of nine group medians, not the median of all 21 brain tracks.

## What the mapping means

The complete metadata mapping is reused from `groups.json` and
`tissue_payload.json` in `data/manuscript_v020_20260909/`. Their SHA256 hashes
are pinned in the adapter and written to every classification receipt. Only
metadata is read for classification, **never saved real or null score values**.

Membership depends on the exact canonical key
`track_name||biosample_name||ontology_curie||data_source`, plus validated raw
`biosample_type`, `biosample_life_stage` and `gtex_tissue`. Empty metadata is
normalized to an empty string. Donor stage is not inferred from cell maturity,
name, disease status or a GTEx prefix.

- Adult frontal cortex, BA9 and anterior cingulate tracks are within Cerebral cortex.
- Embryonic brain tissue is separate from adult tissue. Embryonic neural stem
  cells, neural/glial cultures, hESC-derived cells and neural tumor lines belong
  to Cells & cell lines, **not** Embryo brain tissue.
- GTEx cultured fibroblasts and EBV-transformed lymphocytes belong to Cells &
  cell lines even when the upstream raw material field says tissue.
- Spinal cord, pituitary and peripheral nerve are Non-brain tissues, not Brain9.
- Whole brain is the display label for the original adult region-unspecified
  brain category. It is not an average of the other brain regions.

## Strict manuscript-catalog mode

This release deliberately requires all **371 reviewed track identities** in
the real variant and **every null**. Unknown tracks, missing tracks, changed
classification metadata, nonfinite scores or missing/null-ID mismatches cause
failure with a classification audit. There is no “other brain” fallback, no
substitution from v0.18, no imputation and no silent complete-case deletion.
This rule applies even to exploratory 10-null runs. The requested count is
checked exactly; the UI default is 1,000 per variant.

A future provider catalog change may therefore stop a new analysis. This is
intentional: review the provider metadata and publish a new, separately tested
mapping version. Do not edit the sealed metadata or force old counts onto new
tracks. The current app has no automatic catalog upgrade button.

Duplicate raw rows are collapsed using a median per real track, or per
`(null_id, track_key)` for nulls, **before** calculating the track's null median.
The same track center is subtracted from both real and null scores. All groups
use individual canonical-track medians; null consensus follows the identical
nine-group aggregation. The two display-only pools cannot change Brain9 P,
BH adjustment or cosine similarity.

## Outputs and compatibility

- Single plots: 11 bars with individual track points and counts.
- Multi heatmap: nine Brain9 columns in the table's order; default row order is
  ascending Brain9 consensus. FDR annotations include either significant tail,
  while observed-direction one-sided FDR remains explicitly exploratory.
- Multi matrix/source downloads: all 11 categories, including comparison pools.
- Primary two-sided empirical P: median-recentered null consensus, plus-one
  correction. BH uses the whole requested successful cohort, not a hardcoded
  family of 17. The first input variant remains the cosine reference.
- Cosine: exactly nine finite, uncentered group effects. Zero norms produce NA,
  not zero. Missing features do not trigger pairwise deletion.
- `classification_audit.json` / `.tsv`: mapping version, hashes, observed counts,
  metadata checks and failure reasons; successful jobs expose these downloads.
  Failed-job receipts remain in the private local job's `results/` directory.
- Old local Brain6 jobs remain labeled legacy; this update does not reanalyze,
  relabel or overwrite them. All sealed manuscript artifacts remain unchanged.

Since local.3, and unchanged in 0.24.0, the separate new-run RNA curve uses the same adult **Frontal cortex,
GTEx Brain_Cortex, UBERON:0001870, polyA+ unstranded** track as the saved explorer.
Whole brain remains a valid Brain9 bar category, not the RNA curve source.
See [RNA curve selection](RNA_CURVE.md). Current API weights are not pinned by SDK
0.8.0, so matching the grouping and track does not guarantee matching saved values.
