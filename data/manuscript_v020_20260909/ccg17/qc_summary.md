# Frozen v0.20: 17-variant manuscript cohort

- Only frozen v0.20 gene scores inferred on 2026-09-08 UTC with SDK 0.8.0 are used.
- Serving/building these assets makes no inference calls and generates no new null variants.
- Brain9 is the median of eight adult-region medians plus the pooled median of seven embryo brain-tissue tracks.
- The 153 non-brain tissue and 197 cell/model tracks are display-only pools with all available life stages; neither contributes to Brain9.
- Counts refer to assay tracks, not independent biological replicates. These are model predictions, not experimental expression measurements.
- Direction-selected P/q is exploratory, not a prespecified one-sided test.
- The API requested server_default and did not disclose an immutable model checkpoint. SDK version and rollout boundary are not a weights hash.
- Original matched-null design coordinates can predate v0.20; this is distinct from reuse of earlier numerical predictions.

The three RGPD1 variants are excluded. BH correction is across 17 variants separately for two-sided and direction-selected P; no old BH20 values are reused. The approved Figure3 is 174 x 68 mm. Target-assignment/window warnings remain in target_gene_assignment_qc.tsv.
