# Frozen v0.20 manuscript result

- Only frozen v0.20 gene scores inferred on 2026-09-08 UTC with SDK 0.8.0 are used.
- Serving/building these assets makes no inference calls and generates no new null variants.
- Brain9 is the median of eight adult-region medians plus the pooled median of seven embryo brain-tissue tracks.
- The 153 non-brain tissue and 197 cell/model tracks are display-only pools with all available life stages; neither contributes to Brain9.
- Counts refer to assay tracks, not independent biological replicates. These are model predictions, not experimental expression measurements.
- Direction-selected P/q is exploratory, not a prespecified one-sided test.
- The API requested server_default and did not disclose an immutable model checkpoint. SDK version and rollout boundary are not a weights hash.
- Original matched-null design coordinates can predate v0.20; this is distinct from reuse of earlier numerical predictions.

Run: ptchd1_1mb; input length: 1048576 bp; 1000 matched nulls; 371 tracks.
Standalone empirical P values are provided; no cohort q/FDR is assigned. Original target-assignment warnings are retained in target_gene_assignment_qc.tsv.
