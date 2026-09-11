# v0.24 verification scope and evidence

The recorded fresh-provider run completed all 19 analysis contexts: RBFOX1
16,384 bp, the 17-variant 1,048,576-bp cohort, and PTCHD1 1,048,576 bp. Each
context generated new real scores, 1,000 new null score sets and a Frontal
cortex curve. The successful epoch is `dc23d1efac044e49a9f162e6561673d7`,
completed `2026-09-11T02:55:07.771329+00:00`, using AlphaGenome SDK 0.8.0 and
the provider's unresolved `server_default` model.

## What was independently checked

One provider inference epoch ran through the staged web pipeline. GitHub code
then independently aggregated those same raw score files offline. The two
implementations share their scientific code lineage. This is a check of
implementation parity, not two independent provider experiments or an
independently derived statistical method. The complete local browser submission
path was not used for a second 19-context API experiment.

The matched-null generator used fixed seed `20260527`. All 19 regenerated
design files are byte-identical to their sealed v0.20 design counterparts.
Their scores were freshly requested from the provider, with local score reuse
and fallback disabled. The verification tests reproduction under the same
null design; it does not measure variability across independent null samples.

An earlier interrupted gate stopped after 700 nulls because of a provider error.
That output was excluded. The successful epoch used a new private output root.
No v0.18 numerical data entered the experiment.

## Results

| Comparison | Result |
|---|---|
| Web versus GitHub aggregation, all 19 contexts | Source tables, group summaries, null summaries and consensus/P exactly equal |
| Fresh versus sealed v0.20, 19 contexts | Real raw score, trackwise null median and adjusted real effect: 57/57 context-by-field checks exact |
| Fresh versus sealed, standalone and cohort contexts | Consensus, two-sided empirical P and observed-direction P exact |
| 17-variant Brain9 matrix, P and both BH families | Exact |
| Web versus GitHub cohort cosine | Exact |
| Fresh versus sealed cohort cosine | Maximum absolute difference 2.220446049250313e-16 |
| RBFOX1 16-kb raw/aligned Frontal cortex curve | Exact |
| PTCHD1 1-Mb raw/aligned Frontal cortex curve | Equivalent within serialization precision; reported maximum difference 9.3756382865684e-17 |

The curve comparisons verify coordinates, raw REF/ALT values, aligned values and
the adult GTEx Brain_Cortex track identity (`UBERON:0001870`, polyA plus
RNA-seq, unstranded). The original NPZ/TSV comparison reported the PTCHD1
rounding difference shown above. Rechecking the original raw artifacts with the
v0.24 comparator's round-trip TSV parser produced exact equality for both
RBFOX1 and PTCHD1; finite values, NaN masks and dimensions also passed.

Brain9 has 14 adult tracks in eight categories plus seven Embryo tracks. All
371 catalog tracks were required for each real variant and each null; the
153 non-brain tissue and 197 cell tracks are display-only comparison pools.

## Public evidence and tools

The following reports are the original recorded numerical comparisons. They
contain scientific values and no credential, private root or raw job logs:

- [All 19 contexts](verification/v024/all_contexts_report.json)
- [17-variant cohort](verification/v024/cohort_cross_validation_report.json)
- [Frontal cortex curves](verification/v024/curve_cross_validation_report.json)
- [v0.24 direct curve recheck](verification/v024/curve_review_v024.json)

The v0.24 review added fail-closed checks: a reference mismatch can no longer
leave the overall status as passed; numeric comparisons reject invalid
infinities, finite/NaN mismatches and incompatible shapes. Regression tests
include deliberate mismatches. `scripts/compare_frontal_cortex.py` provides a
portable offline comparison with explicit input and output paths. Its `--help`
describes the required layout. No credential is needed for comparison.

## Version and publication meaning

The v0.24 interface and data presentation serve the sealed v0.20 manuscript
assets. Their bytes, original source release and inference dates are retained.
The verification epoch/date are separate metadata. Version 0.24 does not imply
a new provider run after the verification above, newly sampled null positions,
or an identified backend checkpoint. Future provider runs can differ.

The source distribution does not bundle private 19-context raw jobs, reference
genomes, credentials, logs or host-specific execution configuration. Existing
public manuscript assets remain available. API keys used by local installations
remain within the user's environment and are sent to Google DeepMind only for
the user's authorized analysis requests.
