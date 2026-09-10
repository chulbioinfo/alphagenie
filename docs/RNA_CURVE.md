# Frontal cortex RNA curve

The 0.23.0 distribution retains the track identity introduced in local.3 and used by the v0.21 saved manuscript explorer:

| Field | Required value |
|---|---|
| Ontology | UBERON:0001870 |
| Source / tissue | gtex / Brain_Cortex |
| Biosample | frontal cortex |
| Material / donor stage | tissue / adult |
| Assay | polyA plus RNA-seq |
| Strand | `.` (unstranded) |
| Track name | UBERON:0001870 gtex Brain_Cortex polyA plus RNA-seq |

Selector ID: `frontal_cortex_gtex_brain_cortex_unstranded_v1`, implemented in
`worker/rna_curve.py`. SDK `name`/`strand` and exported `track_name`/`track_strand`
column names are supported; conflicting aliases are rejected. `nonzero_mean`
is recorded when returned but is not an identity criterion.

## Selection and validation

New inference requests human RNA_SEQ with `ontology_terms=["UBERON:0001870"]`.
Ontology alone is insufficient because ENCODE embryonic cortex shares this ID.
Each REF and ALT output must have exactly one match for the entire contract.
Channels are selected independently, so reordered channels cannot pair different
tissues. A hardcoded saved channel index is never used.

Both outputs must cover the exact requested interval at 1-bp resolution.
Each channel dimension must agree with its metadata; selected raw predictions
must be finite. The selector records both channel indices and both metadata
records. Missing or ambiguous tracks produce an unavailable curve, not a Whole
brain, BA9/DLPFC, ENCODE, embryo, different assay or stranded substitute.
Valid matched-null scores are not replaced or discarded merely because the
additional curve is unavailable.

## Coordinate projection and artifacts

The existing reference-coordinate projection is retained: deletions zero only
deleted reference positions, insertions collapse their shared anchor and
inserted segment by maximum, downstream ALT indices shift by the net insertion
length, and unmappable boundaries remain NaN. Raw predictions are preserved;
already aligned values are not projected again.

- `frontal_cortex_prediction_raw.tsv`: selected, unprojected REF/ALT arrays.
- `frontal_cortex_prediction.tsv`: aligned reference-coordinate values.
- `frontal_cortex_prediction_status.json`: exact track selection, independent
  REF/ALT metadata, requested interval, resolution, inference timestamps and
  alignment checksums.
- `gene_model.tsv`: annotation for the same prediction interval.

The curve plots direct positional RNA prediction and `ALT − REF`; it does not
plot the matched-null-adjusted GeneMaskLFC statistic used by the Brain9 bars.
Whole brain remains one of the Brain9 adult bar categories.

## Cache and upgrade behavior

Cache keys include variant alleles, input length, target gene, reference/SDK/run
identity, the full track specification and selection version. Hits also require
matching tissue, REF/ALT identities, requested interval, resolution, aligned
variant and raw/aligned SHA256 hashes. Generations are published atomically;
a failed refresh cannot display a prior curve as a fresh result.

Old Whole brain caches and job files do not satisfy the new identity. They are
not renamed, relabeled, overwritten or automatically reanalyzed. Their original
downloads remain available with a legacy curve notice. Starting a new analysis
requires explicit consent and uses the user's own API key.

The SDK pin does not pin provider weights. Matching the saved track and grouping
does not guarantee reproducing September 2026 values. No live API inference was
performed while implementing this change; see [validation](VALIDATION.md).
