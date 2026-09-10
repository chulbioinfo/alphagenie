# Validation record — 2026-09-10

Package: **0.21.0-local.1**. Tests used a development Python **3.11.15** environment with AlphaGenome **0.8.0** and the versions in `requirements-lock.txt`. Test credentials were synthetic canaries, not real keys. Test DBs/state/reference fixtures were isolated temporary directories. **No real AlphaGenome inference or provider authentication request was made.** The public website and its operating environment were not changed.

## Passed

- Python unittest: **39 tests** — local Host/Origin/token/consent checks, input/REF/annotation validation, private-file permissions, in-repository/symlink state rejection, key redaction in subprocess logs/JSON/SQLite, analysis lock inheritance/recovery, storage-failure cleanup, shutdown race handling, no legacy run mode, partial-cohort and missing-reference rejection, Whole brain ontology guard, HTML label escaping, indel coordinate alignment and null completeness.
- Node test runner: **6 tests** — cohort order/BH table, all 371 tracks and category counts, escaping, export options, interactive dot pointer/keyboard behavior and local UI source contract.
- Python compilation and JavaScript syntax checks passed. `pip check`: no broken installed requirements.
- Saved release: **70 assets**, all byte hashes identical to the sealed v0.20 manifest. **55 HTTP downloads** byte-identical to their original counterparts; all three saved result payloads unchanged.
- RBFOX1 and PTCHD1: raw `1000 × 371` null arrays reproduce track medians, adjusted effects and Brain9 empirical P. A synthetic 1,000-null engine test independently reproduces exported consensus/P and verifies unchanged sampled design.
- Stacked PDF: requested **174 × 136 mm**, 6.5-point configuration served correctly; invalid small-font requests rejected. Original saved PDFs remain separate immutable files.
- Isolated pipeline audit: ten internal modules and all six pipeline scripts import from this package, without loading the original working repository. All six script `--help` entry points run from another directory. Core statistical formulas and alignment logic were retained; local guard changes are described in METHODS.md.
- `doctor` succeeds with a clean temporary state directory, no key and no references, verifying offline saved-result readiness.
- Source release scanner: source allowlist, no symlinks/private runtime files, secret-pattern/private-path scan, per-file GitHub size threshold, sealed-data hashes. This is a heuristic scan, not proof against every possible secret or privacy leak.

## Not yet validated / release gates

- Clean dependency installation on a new macOS/Linux/WSL machine; the existing development environment was used for these checks.
- Actual key authentication, provider quota behavior, end-to-end fresh scoring/prediction, 1,000-null runtime/disk requirements and failure/retry behavior against Google's service.
- Screenshot or browser-driven visual QA of the new local analysis form. Static syntax, source contracts, numerical HTTP responses and existing interactive chart tests were checked; visual correctness on every device is not claimed.
- A fresh Brain9 / frontal-cortex inference adapter or interactive/custom-dimension exporter for new jobs: **not implemented**. Current new jobs use the original Brain6 / Whole brain engine and renderer.
- Code license selection, contributor/data redistribution rights, maintainer configuration and real GitHub CI execution. The local workflow file is supplied, not yet run on GitHub.

Re-run `scripts/check.sh` after any source/dependency changes. New inference dates/checkpoints must be recorded from actual runs, not assigned by a render or test pass.
