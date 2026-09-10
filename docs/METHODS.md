# Methods and provenance

## Version meaning

`0.21.0-local.1` names this local distribution. **v0.21** is the UI lineage; **v0.20** is the preserved scientific engine/data lineage. The older internal pipeline directory name in the source history does not mean that this package uses v0.18 predictions. Six original pipeline scripts are included under `pipeline/scripts/`; no v0.18 numerical cache is shipped and local job entry rejects demo/legacy mode.

### Saved manuscript workflow

The hash-verified release `alphagenie_manuscript_v020_20260909` contains Figure 2 RBFOX1 16 kb, Figure 3 17 variants at 1 Mb (three RGPD1 entries excluded), and Figure 4 PTCHD1 1 Mb. Each analysis uses **1,000 matched nulls**. The standalone RBFOX1 16 kb result is not its 1 Mb cohort result.

Brain9 = median of nine category medians: 14 adult tracks in eight anatomical categories plus seven embryo brain tracks in one category. Display categories and counts: cerebral cortex 4, hippocampal formation 1, basal ganglia/striatum 3, amygdala 1, diencephalic 1, midbrain 1, cerebellum 2, Whole brain 1, Embryo 7; non-brain tissues 153 and cells/lines 197 are display-only. Tracks are assays, **not independent biological replicates**.

The saved RNA curve is GTEx **Brain_Cortex, UBERON:0001870**, polyA+ RNA-seq, unstranded; not BA9 and not Whole brain. Scores were obtained 2026-09-08 UTC; the PTCHD1 cortex curve was obtained 2026-09-10 UTC. Curve inference and score inference dates are recorded separately. Viewing/reformatting does not create a new inference timestamp.

### Fresh local workflow — original Brain6 engine

1. Parse forward-strand, 1-based GRCh38 VCF-style alleles. Check supported lengths (16,384/131,072/524,288/1,048,576), simple indel representation, local REF match and one target-gene annotation overlapping the input interval. These are eligibility/QC checks, not proof of biological target assignment.
2. Use AlphaGenome Python SDK **0.8.0**, recommended RNA_SEQ variant scoring, and select target-gene **GeneMaskLFCScorer** output. Preserve raw returned scores and scorer representation.
3. Generate class-matched null variants in the same fixed input interval; seed **20260527**. The worker passes the requested null count, default **1,000** in this local UI. Deletions preserve deletion length with CG/GC criteria relaxed in stages; substitutions prefer matched REF/ALT then relax to the same edited offsets; insertions place the same inserted sequence at other positions.
4. Score real/null variants, collapse duplicate track rows by median, subtract the trackwise null median from the real GeneMaskLFC score, then compute group medians and the median of the six group medians.
5. Six primary groups: **Whole brain; Cortex/frontal cortex; Hippocampus; Basal ganglia; Cerebellum; Other brain**. They are **not adult-only**. Neural progenitors, neural/glial cells and non-brain groups are not substituted for missing primary brain groups.
6. Null consensus uses the same groups. Real results require all six finite groups. At requested null depth ≥1,000, all requested nulls must have complete primary-group coverage; otherwise the analysis fails. At exploratory depths, incomplete nulls may be excluded with an explicit coverage receipt and effective count.
7. Two-sided empirical P compares the observed absolute statistic to the null-consensus distribution after recentering by its median, using the **plus-one** correction `(exceedances + 1)/(N + 1)`. Observed-direction P is exploratory and direction-selected after seeing the effect, not a prespecified one-sided test.
8. A standalone result has an empirical P, not a cohort FDR. Historical compatibility fields named `bh_fdr_two_sided` in a single result may equal P; do not interpret them as multi-variant correction.
9. For multi-variant runs, all requested variants must succeed before cohort summary. BH correction is then across the requested family; cosine compares the six-group effect vector to the **first requested row**, using the original engine's row-order/plotting conventions. Partial failures retain successful individual results but do not produce a reduced-family cohort. Undefined cosine (e.g. a zero vector) is not evidence of biological dissimilarity.
10. The additional curve predicts **Whole brain UBERON:0000955** with the original engine, using reference-coordinate alignment for REF/ALT indels. Per-position `ALT − REF` curve values are not the adjusted GeneMaskLFC statistic shown by the bars.

## Null model limitations

This is not a complete match for TSS distance, replication phase, CpG, mappability or every genomic confounder. The inherited null design string `same_fixed_1Mb_interval` is a legacy descriptive field even when the true input is 16 kb; use the recorded `fixed_interval` and `sequence_length` as authoritative. No null positions/scores are silently borrowed from the frozen manuscript or v0.18 results.

## Model and reproduction limits

New local runs record a fresh UUID epoch, actual scoring/prediction start/end UTC times, installed SDK, scorer settings, input/output hashes, annotation path/stat, requested model `server_default`, and **unresolved provider checkpoint**. Pinning the SDK does not pin Google backend weights. Do not equate a current API execution with a July rollout or the September saved inference. Score sidecars refuse incompatible/unprovenanced appends.

The existing scientific calculations are reused; local patches affect credential handling, portability, preflight, run-mode restrictions, error redaction, cohort completeness and truthful provenance labels. Missing Whole brain metadata now fails closed instead of selecting an unrelated first track, and a missing cosine reference is not replaced. See `SOURCE_ORIGIN.json` for copied file hashes. Newly rendered figures can vary with installed fonts; the original sealed figures retain their hashes.

## Reading and citing

- [Official AlphaGenome client](https://github.com/google-deepmind/alphagenome)
- [Official installation guide](https://www.alphagenomedocs.com/installation.html)
- [AlphaGenome paper](https://doi.org/10.1038/s41586-025-10014-0)

For a manuscript, report your exact local commit/release, SDK, reference release/checksums, timestamp, target variant/gene, input length, null design/seed/count, grouping version, effective coverage, test family and requested/unresolved model fields. Do not use this exploratory tool for clinical decisions.
