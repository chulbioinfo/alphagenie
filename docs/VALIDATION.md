# Validation records

## v0.24.0 review — 2026-09-11

The [verification record](VERIFICATION_v0.24.md) documents the completed
19-context live-provider experiment and the separate offline web/GitHub
aggregation comparison. Each context used 1,000 freshly scored nulls under the
same deterministically regenerated design. Full source/summary comparisons
matched; curve and cosine serialization tolerances are reported explicitly.

The release review strengthens fresh-epoch validation and makes comparison
failures reject invalid reference results, infinities, NaN-mask mismatches and
incompatible dimensions. Release tests run offline using synthetic credentials
and temporary state. The pinned dependency versions and all 70 sealed assets
are retained. Final local validation passed **138 Python tests and 8 Node
UI tests**; the public implementation passed **166 Python tests and 14 Node
UI tests**. External sockets and provider factories were blocked during the
Python regressions, with loopback HTTP permitted. The 63-package installed
inventory exactly matched the locks, and the dated public OSV query returned
no advisory matches. The strict recorded-report check passed, and a direct
v0.24 curve recheck with round-trip TSV parsing matched both genes exactly.
GitHub CI is checked separately for the published commit.

## v0.23.0 integration — 2026-09-10

Distribution **0.23.0**, interface **0.23**, engine/data **0.20**, SDK **0.8.0**.
The versioned source passed **118 Python tests and 8 Node UI-logic tests**.
Python regressions used isolated temporary state with external sockets/provider
channels blocked; no actual API key was read and no provider request was made.

- Native deletion/insertion/substitution design IDs, compatible aliases, dual
  columns, literal `NA`/leading-zero IDs, malformed IDs, exact null counts and
  strict track/finite-score validation are covered end-to-end.
- All **70 sealed manuscript assets** remain hash-identical. Scientific formulas,
  sampling, Brain9 membership, Frontal cortex selection and the **63-package**
  installed inventory are unchanged.
- An existing user-triggered RBFOX1 16-kb run had already produced 371 real
  track scores and ten complete 371-track nulls before the prior ID-reader
  failure. A separate, network-blocked diagnostic replay of those scores passed
  corrected summary, Brain9, single-job finalization, PDF/SVG/PNG/HTML and 13
  local download handlers. The original failed job and files were preserved.
  Cortex prediction was explicitly mocked as unavailable, not newly inferred.
- Cohort null exports are registered only when current child exports are all
  available; string IDs survive combination, and stale exports are withheld.
- Existing v0.22 native CI passed on macOS arm64/Intel and Linux arm64/x86_64
  ([record](https://github.com/chulbioinfo/alphagenie/actions/runs/34514964806)).
  That historical result is not evidence of a v0.23 CI run; inspect the current
  commit's GitHub Actions result separately.

These tests do not establish live-provider end-to-end success, a generated new
cortex curve, clinical validity or multi-user isolation. New analysis remains
explicit and can consume provider quota. Final source-archive identity, current
CI and deployment status must be checked for the release actually published.
Older records below are preserved as historical evidence.

## v0.22.0 integration — 2026-09-10

Distribution **0.22.0**, interface **0.22**, engine/data **0.20**, AlphaGenome SDK **0.8.0**. No live AlphaGenome inference or provider-authentication request was made by these checks. The scientific package versions, sealed manuscript values, original inference dates and historical record below are preserved.

### Completed checks

- A fresh isolated CPython 3.11 virtual environment on macOS arm64 installed the reviewed hashed wheels: **61 unchanged runtime packages**, plus pip **26.2.1** and setuptools **84.0.0**. `pip check` passed and the installed inventory exactly matched all **63** pins. Scientific SDK and binary dependency imports passed without creating an API client.
- Official PyPI metadata matched the reviewed SHA256 hashes and wheel coverage for macOS 12+ arm64/Intel and Linux glibc 2.28+ aarch64/x86_64. Hash-checked pip resolution dry runs passed for Linux x86_64/aarch64 and macOS Intel. These are not native execution tests on those platforms.
- Public OSV name/version queries returned **no advisory matches for all 63 pins** on the review date. Failure or incomplete responses fail closed. No match is not proof of package safety and can change with newly published advisories.
- Final `scripts/check.sh` run in the fresh hash-locked environment passed **108 Python tests and 8 Node tests**, covering offline scientific behavior, request boundaries, dependency packaging and the no-login private-computer UI.
- All **70 sealed manuscript assets** retain their original hashes. The **55 original HTTP downloads** passed the byte-preservation checks. No scores, null arrays or inference dates were regenerated or relabeled.
- An independent frontend review of the final no-login flow found no blocking issue within the expressly trusted private-computer boundary. This is not a claim of authentication, protection against other local users or live-provider validation.
- Source archive verification must be run on the final generated release artifact; per-file counts and archive hashes are not inferred from an earlier tree.

### Remaining stable-release gates

Actual native CI completion, independent clean-machine checks, real eligible-key end-to-end inference, quota/runtime/disk/failure behavior, and licensing/redistribution approvals remain to be verified. A configured workflow, dry run or source release note does not establish a GitHub release or public deployment. This package remains a research preview, with no local-user authentication; other local programs/users may access its loopback endpoints.

## Prior validation — 0.21.0-local.3, 2026-09-10

The following historical **61 Python / 7 Node** record describes the prior package only, including limitations and files that existed at that time. It is not the final 0.22 validation count or a statement about the current publication state.

Package: **0.21.0-local.3**. Tests used a development Python **3.11.15** environment with AlphaGenome **0.8.0** and the versions in `requirements-lock.txt`. Test credentials were synthetic canaries, not real keys. Test DBs/state/reference fixtures were isolated temporary directories. **No real AlphaGenome inference or provider authentication request was made.** The public website and its operating environment were not changed.

### Passed in the prior package

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

### Prior unvalidated items / release gates

- Clean dependency installation on a new macOS/Linux/WSL machine; the existing development environment was used for these checks.
- Actual key authentication, provider quota behavior, end-to-end fresh scoring/prediction, 1,000-null runtime/disk requirements and failure/retry behavior against Google's service.
- Screenshot or browser-driven visual QA of the new local analysis form. Static syntax, source contracts, numerical HTTP responses and existing interactive chart tests were checked; visual correctness on every device is not claimed.
- The Brain9 and Frontal cortex adapters are implemented and tested offline, but end-to-end fresh inference remains untested against the live provider. The interactive/custom-dimension exporter for new jobs is **not implemented**; new jobs use the existing renderer with Frontal cortex labels/data. Saved interactive/cortex exports are unchanged.
- Code license selection, contributor/data redistribution rights, maintainer configuration and real GitHub CI execution. The local workflow file is supplied, not yet run on GitHub.

Re-run `scripts/check.sh` after any source/dependency changes. New inference dates/checkpoints must be recorded from actual runs, not assigned by a render or test pass.
