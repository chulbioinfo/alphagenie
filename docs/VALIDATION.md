# Validation record — 2026-09-10

Package: **0.21.0-local.3**. Tests used a development Python **3.11.15** environment with AlphaGenome **0.8.0** and the versions in `requirements-lock.txt`. Test credentials were synthetic canaries, not real keys. Test DBs/state/reference fixtures were isolated temporary directories. **No real AlphaGenome inference or provider authentication request was made.** The public website and its operating environment were not changed.

## Passed

- Python unittest: **61 tests** — prior local security, validation, locking, alignment, null-export and Brain9 tests, plus exact Frontal cortex selection, missing/ambiguous metadata, independently reordered REF/ALT channels, interval/resolution/finite-value checks, old-cache separation, failed-refresh isolation and English-language regressions. Old Brain6 job and legacy curve labels are preserved.
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
- Exact curve selector matches both saved v0.21 metadata records. Synthetic TrackData and a mocked provider verify that inference requests UBERON:0001870, picks adult GTEx Brain_Cortex in both REF/ALT outputs, emits frontal-cortex artifact names, and preserves recorded inference dates on valid cache hits. These are offline integration tests, not live API results.
- Independent network-blocked review reran the nine curve tests and reprojected the packaged raw curves. Results exactly match the saved aligned full-window data for RBFOX1 (16,384 bases) and PTCHD1 (1,048,576 bases), including all 27 unavailable PTCHD1 boundary positions.
- English review: all distributed prose and comments are English. The release guard checks **134 text files**, including decoded JSON and gzip text, for non-English-script regressions. Scientific symbols are preserved. Bundled numerical metadata and figures were inspected separately; all 70 sealed assets remain byte-identical. The old `README.ko.md` path now contains only an English redirect.

## Not yet validated / release gates

- Clean dependency installation on a new macOS/Linux/WSL machine; the existing development environment was used for these checks.
- Actual key authentication, provider quota behavior, end-to-end fresh scoring/prediction, 1,000-null runtime/disk requirements and failure/retry behavior against Google's service.
- Screenshot or browser-driven visual QA of the new local analysis form. Static syntax, source contracts, numerical HTTP responses and existing interactive chart tests were checked; visual correctness on every device is not claimed.
- The Brain9 and Frontal cortex adapters are implemented and tested offline, but end-to-end fresh inference remains untested against the live provider. The interactive/custom-dimension exporter for new jobs is **not implemented**; new jobs use the existing renderer with Frontal cortex labels/data. Saved interactive/cortex exports are unchanged.
- Code license selection, contributor/data redistribution rights, maintainer configuration and real GitHub CI execution. The local workflow file is supplied, not yet run on GitHub.

Re-run `scripts/check.sh` after any source/dependency changes. New inference dates/checkpoints must be recorded from actual runs, not assigned by a render or test pass.
