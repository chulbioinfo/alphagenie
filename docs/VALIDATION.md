# Validation record — 2026-09-10

Package: **0.21.0-local.2**. Tests used a development Python **3.11.15** environment with AlphaGenome **0.8.0** and the versions in `requirements-lock.txt`. Test credentials were synthetic canaries, not real keys. Test DBs/state/reference fixtures were isolated temporary directories. **No real AlphaGenome inference or provider authentication request was made.** The public website and its operating environment were not changed.

## Passed

- Python unittest: **50 tests** — prior local security, validation, locking, alignment and null-export tests plus Brain9 mapping/counts, donor-stage/material drift, unknown/missing tracks, nonfinite scores, null ID/depth mismatches, duplicate weighting, display-pool exclusion, strict nine-feature cosine, zero-norm NA and preservation of old Brain6 job labels.
- Node test runner: **7 tests** — cohort order/BH table, all 371 tracks and category counts, escaping, export options, interactive dot pointer/keyboard behavior, local UI source contract and fresh Brain9/curve explanations.
- Python compilation and JavaScript syntax checks passed. `pip check`: no broken installed requirements.
- Saved release: **70 assets**, all byte hashes identical to the sealed v0.20 manifest. **55 HTTP downloads** byte-identical to their original counterparts; all three saved result payloads unchanged.
- RBFOX1 and PTCHD1: the new canonicalization adapter processes each complete raw `1000 × 371` null cache with real metadata. Track centers, adjusted real effects, Brain9 consensus and empirical P match saved values exactly.
- All 17 cohort variants: independently remapped track-level scores, nine category medians, 1,000 category-null vectors, consensus and empirical P reproduce saved results. BH and cosine match within floating-point precision. The complete cohort exporter retains 11 matrix columns while its heatmap/cosine contract contains exactly nine categories.
- A synthetic 1,000-null worker test reproduces exported consensus/P and verifies unchanged sampled design. Missing original design now fails instead of skipping ID verification. No tests regenerate the saved null arrays or make them new API results.
- Stacked PDF: requested **174 × 136 mm**, 6.5-point configuration served correctly; invalid small-font requests rejected. Original saved PDFs remain separate immutable files.
- Isolated pipeline audit: ten internal modules and all six pipeline scripts import from this package, without loading the original working repository. All six script `--help` entry points run from another directory. Core statistical formulas and alignment logic were retained; local guard changes are described in METHODS.md.
- `doctor` succeeds with a clean temporary state directory, no key and no references, verifying offline saved-result readiness.
- Source release scanner: source allowlist, no symlinks/private runtime files, secret-pattern/private-path scan, per-file GitHub size threshold, sealed-data hashes. This is a heuristic scan, not proof against every possible secret or privacy leak.

## Not yet validated / release gates

- Clean dependency installation on a new macOS/Linux/WSL machine; the existing development environment was used for these checks.
- Actual key authentication, provider quota behavior, end-to-end fresh scoring/prediction, 1,000-null runtime/disk requirements and failure/retry behavior against Google's service.
- Screenshot or browser-driven visual QA of the new local analysis form. Static syntax, source contracts, numerical HTTP responses and existing interactive chart tests were checked; visual correctness on every device is not claimed.
- The fresh-score Brain9 adapter is implemented and tested offline, but end-to-end fresh inference remains untested against the live provider. A new frontal-cortex curve selector and interactive/custom-dimension exporter for new jobs are **not implemented**. New jobs still use the original Whole brain curve/renderer; saved interactive/cortex exports are unchanged.
- Code license selection, contributor/data redistribution rights, maintainer configuration and real GitHub CI execution. The local workflow file is supplied, not yet run on GitHub.

Re-run `scripts/check.sh` after any source/dependency changes. New inference dates/checkpoints must be recorded from actual runs, not assigned by a render or test pass.
