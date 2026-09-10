# Methods and provenance

## Version meaning

`0.23.0` names this local distribution. **v0.23** is the current interface version, continuing the v0.21/v0.22 UI lineage; **v0.20** is the preserved scientific engine/data lineage. The 0.23 release corrects matched-null ID compatibility and result export registration while retaining the 0.22 packaging and request safeguards. Scientific formulas, saved scores, null arrays, track selection and recorded inference dates are unchanged. The older internal pipeline directory name in the source history does not mean that this package uses v0.18 predictions. Six original pipeline scripts are included under `pipeline/scripts/`; no v0.18 numerical cache is shipped and local job entry rejects demo/legacy mode.

### Saved manuscript workflow

The hash-verified release `alphagenie_manuscript_v020_20260909` contains Figure 2 RBFOX1 16 kb, Figure 3 17 variants at 1 Mb (three RGPD1 entries excluded), and Figure 4 PTCHD1 1 Mb. Each analysis uses **1,000 matched nulls**. The standalone RBFOX1 16 kb result is not its 1 Mb cohort result.

Brain9 = median of nine category medians: 14 adult tracks in eight anatomical categories plus seven embryo brain tracks in one category. Display categories and counts: cerebral cortex 4, hippocampal formation 1, basal ganglia/striatum 3, amygdala 1, diencephalic 1, midbrain 1, cerebellum 2, Whole brain 1, Embryo 7; non-brain tissues 153 and cells/lines 197 are display-only. Tracks are assays, **not independent biological replicates**.

The saved RNA curve is GTEx **Brain_Cortex, UBERON:0001870**, polyA+ RNA-seq, unstranded; not BA9 and not Whole brain. Scores were obtained 2026-09-08 UTC; the PTCHD1 cortex curve was obtained 2026-09-10 UTC. Curve inference and score inference dates are recorded separately. Viewing/reformatting does not create a new inference timestamp.

### Fresh local workflow — v0.20 scoring with versioned manuscript Brain9

1. Parse forward-strand, 1-based GRCh38 VCF-style alleles. Check supported lengths (16,384/131,072/524,288/1,048,576), simple indel representation, local REF match and one target-gene annotation overlapping the input interval. These are eligibility/QC checks, not proof of biological target assignment.
2. Use AlphaGenome Python SDK **0.8.0**, recommended RNA_SEQ variant scoring, and select target-gene **GeneMaskLFCScorer** output. Preserve raw returned scores and scorer representation.
3. Generate class-matched null variants in the same fixed input interval; seed **20260527**. The worker passes the requested null count, default **1,000** in this local UI. Deletions preserve deletion length with CG/GC criteria relaxed in stages; substitutions prefer matched REF/ALT then relax to the same edited offsets; insertions place the same inserted sequence at other positions.
4. Validate real/null metadata against the hash-bound manuscript catalog in `worker/brain9.py`. Canonical key = `track_name||biosample_name||ontology_curie||data_source`; missing strings are normalized to empty strings. Also require identical biosample type, donor life stage and GTEx tissue fields. Unrecognized, missing or changed tracks fail rather than being inferred from names or pooled as “other.”
5. Require the full 371-track catalog and finite scores for the real variant and every null, at every requested depth. Null ID sets must equal the original sampled design when present; actual API jobs generate this design. Duplicate real rows are collapsed by track median; duplicate null rows by `(null_id, track_key)` median **before** computing the trackwise null median. Subtract that median from real/null canonical raw scores, then take within-group track medians.
6. Brain9 consensus = median of **eight adult category medians plus one Embryo median**. Embryo directly pools its seven brain-tissue tracks, not three region medians. Non-brain tissues and Cells & cell lines directly pool all their tracks across available stages and are excluded from Brain9 inference. No neural/glial cells, spinal cord or pituitary are substituted for adult/embryonic brain tissue. Classification audits, counts, null group medians and null consensus are exported. See [full definition and strict catalog policy](BRAIN9.md).
7. Two-sided empirical P compares the observed absolute statistic to the null-consensus distribution after recentering by its median, using the **plus-one** correction `(exceedances + 1)/(N + 1)`. Observed-direction P is exploratory and direction-selected after seeing the effect, not a prespecified one-sided test.
8. A standalone result has an empirical P, not a cohort FDR. Historical compatibility fields named `bh_fdr_two_sided` in a single result may equal P; do not interpret them as multi-variant correction.
9. For multi-variant runs, all requested variants must succeed before cohort summary. BH correction is then across the requested family; cosine compares the complete nine-group, uncentered Brain9 effect vector to the **first requested row**, with ascending-consensus row order by default. The heatmap uses the nine Brain9 categories; the source matrix retains all 11 categories. Partial failures retain successful individual results but do not produce a reduced-family cohort. Missing/nonfinite category values fail. Zero-norm cosine is exported as missing and labeled NA, never substituted with zero.
10. The additional curve selects adult **Frontal cortex, GTEx Brain_Cortex, UBERON:0001870, polyA plus RNA-seq, unstranded (`.`)** as in the v0.21 saved explorer. Require a unique exact metadata match independently in REF and ALT, equal requested intervals, 1-bp resolution and finite raw arrays. Missing/ambiguous tracks yield an unavailable curve without substituting Whole brain, BA9, ENCODE or embryo. Reference-coordinate alignment for REF/ALT indels is unchanged; see [RNA curve contract](RNA_CURVE.md). Per-position `ALT − REF` curve values are not the adjusted GeneMaskLFC statistic shown by the bars.

## Null model limitations

This is not a complete match for TSS distance, replication phase, CpG, mappability or every genomic confounder. The inherited null design string `same_fixed_1Mb_interval` is a legacy descriptive field even when the true input is 16 kb; use the recorded `fixed_interval` and `sequence_length` as authoritative. No null positions/scores are silently borrowed from the frozen manuscript or v0.18 results.

## Model and reproduction limits

New local runs record a fresh UUID epoch, actual scoring/prediction start/end UTC times, installed SDK, scorer settings, input/output hashes, annotation path/stat, requested model `server_default`, and **unresolved provider checkpoint**. Pinning the SDK does not pin Google backend weights. Do not equate a current API execution with a July rollout or the September saved inference. Score sidecars refuse incompatible/unprovenanced appends.

The v0.20 score/null generation is reused, and the local.2 adapter applies the manuscript Brain9 aggregation with canonical-before-centering duplicate handling; other local patches affect credential handling, portability, preflight, run-mode restrictions, error redaction, cohort completeness and truthful provenance labels. Missing Frontal cortex metadata now fails closed instead of selecting an unrelated track, and a missing cosine reference is not replaced. The local.3 curve adapter validates identity, window, alignment and hashes on cache access; old Whole brain curves are not relabeled. See `SOURCE_ORIGIN.json` for copied file hashes. Newly rendered figures can vary with installed fonts; the original sealed figures retain their hashes.

## Reading and citing

- [Official AlphaGenome client](https://github.com/google-deepmind/alphagenome)
- [Official installation guide](https://www.alphagenomedocs.com/installation.html)
- [AlphaGenome paper](https://doi.org/10.1038/s41586-025-10014-0)

For a manuscript, report your exact local commit/release, SDK, reference release/checksums, timestamp, target variant/gene, input length, null design/seed/count, grouping version, effective coverage, test family and requested/unresolved model fields. Do not use this exploratory tool for clinical decisions.
