# AlphaGENIE Local

**AlphaGENome-Integrated Explorer** — distribution **0.24.0**, interface and verified data presentation **v0.24**, with preserved v0.20 scientific source lineage.

Download this repository, run the interface on your own computer, and use **your own AlphaGenome API key**. No AlphaGENIE account or operator-hosted API proxy is involved.

> **Privacy:** This distribution contains no API key collection endpoint, telemetry or automatic feedback upload to AlphaGENIE. Keys stay in your local environment and are used to authenticate requests directly to Google DeepMind's AlphaGenome API. New inference sends variants/intervals and your key to Google; it is **not fully offline computation**. See [Privacy](docs/PRIVACY.md).

[Installation](docs/INSTALL.md) · [Release notes](docs/RELEASE_NOTES_v0.24.md) · [Methods](docs/METHODS.md) · [Development plan](docs/DEVELOPMENT_PLAN.md) · [Security](SECURITY.md)

## Quick start

Supported wheel targets: **CPython 3.11**, macOS 12+ (Apple Silicon/Intel), or Linux/WSL2 with glibc 2.28+ (x86_64/aarch64). Native Windows and Alpine/musl are unsupported. Node is only needed for developer tests. Setup installs the reviewed, hash-verified runtime and installer locks into a dedicated `.venv`.

```sh
bash scripts/setup.sh
source .venv/bin/activate
python -m alphagenie serve
```

Open **http://127.0.0.1:8877/**. No account, login, password or recovery step is required. Use the exact numeric address, not `localhost`. Keep the terminal open; Ctrl+C stops the server and interrupts its active analysis. Saved examples work without an API key, genome references or a new API call.

**Private-computer warning:** Run only on your own trusted computer under a single OS user. Never use a shared server, shared workstation account, tunnel, reverse proxy or LAN/public binding. There is no local-user authentication: other programs or OS users able to reach the loopback port may read configuration/status and private job outputs or invoke local endpoints. Exact Host/Origin and CSRF checks are browser-request safeguards, not user isolation; a warning is not access control. See [local operating limits](docs/INSTALL.md#private-computer-only).

To run new analyses, first install `samtools` and prepare GRCh38 FASTA + `.fai` and GENCODE v46 GTF (see installation guide):

```sh
python -m alphagenie key set
python -m alphagenie configure --fasta /path/to/hg38.fa --gtf /path/to/gencode.v46.annotation.gtf.gz
python -m alphagenie doctor
```

The key prompt is hidden. Never paste a real key into a shell command, issue, notebook committed to Git, or this repository. Default configuration and results live under `~/.alphagenie/`, outside the checkout. The key file is **owner-only, but not encrypted**. Alternatively provide `ALPHA_GENOME_API_KEY` through your own secure environment; it is not persisted by this application.

In **My analyses**, paste a TSV, choose the input length and null count, review the transmission consent, and run. One row runs a single variant; 2–20 rows run a comparison. Default: **1,000 nulls per variant**. Large analyses may take substantial time and disk space and consume your API quota. No automatic resume after interruption.

## Saved results and fresh analysis

| | Saved manuscript explorer | New local analysis |
|---|---|---|
| UI | v0.24 | v0.24 local workspace |
| Numerical source | Sealed v0.20 artifacts, reproduced in the September 11 verification; 1,000 nulls each | Fresh inference using the reviewed Brain9 engine |
| Brain endpoint | Brain9: 8 adult categories + Embryo | Same versioned **Brain9** membership (8 adult + Embryo) |
| RNA curve | Frontal cortex, UBERON:0001870 | Same adult GTEx Brain_Cortex, polyA+, unstranded track |
| Multi-variant family | Fixed 17 variants, RGPD1 excluded | All requested variants must complete; first row is cosine reference |
| Network | None for local viewing/export | Google DeepMind API on explicit run |

Both workflows display **11 categories** for single variants: the nine Brain9 categories, Non-brain tissues, and Cells & cell lines. Only Brain9 enters primary statistics and cosine; multi-variant heatmaps show those nine categories, while the downloadable matrix retains all 11. The reviewed catalog has 371 tracks (14 adult brain + 7 embryonic brain + 153 non-brain tissue + 197 cells). New/missing tracks or changed classification metadata stop analysis for review; no guessed grouping or legacy fallback. See [Brain9 specification](docs/BRAIN9.md).

New RNA curves retain the [exact Frontal cortex selector introduced in v0.21](docs/RNA_CURVE.md), with no Whole brain, BA9, ENCODE or embryo fallback. All active documentation, comments and interface text are in English.

The SDK is pinned to **0.8.0**, not to an immutable provider checkpoint. The recorded September 11 verification freshly scored 19 contexts with 1,000 nulls each and reproduced the saved results. The fixed seed regenerated the same null designs; web and GitHub code separately aggregated the same fresh raw scores. This verifies reproducibility for that epoch, not future backend behavior. See the [verification record](docs/VERIFICATION_v0.24.md) and [Methods](docs/METHODS.md). No v0.18 numerical fallback is shipped or used.

Included: interactive saved-result dots, source-track search, stacked custom-dimension PDF export, original Figure 2/3/4 PDFs, saved null arrays/source tables, single/multi inference, matched-null generation, empirical statistics, BH/cosine, local job status and downloads. New-run figures currently use the original engine renderer; the configurable stacked exporter applies to saved single-variant results only.

## Repository layout

```text
alphagenie/       local CLI, private config, reference preflight, server, job runner
app/             v0.24 interface and saved-result rendering (retained v021 paths)
worker/          v0.20 inference/statistics/plotting engine, local safety patches
pipeline/scripts/ real/null scoring, indel/SNV null generation, reference QC
data/            hash-verified v0.20 manuscript examples (no credentials)
examples/        TSV inputs, not automatically executed
docs/            installation, methods, privacy, architecture, development/publishing plans
tests/           offline scientific and local-security regression tests
scripts/         setup, start, check, release scan and source archive tools
```

## Use, attribution and release status

AlphaGenome is developed by **Google DeepMind**; AlphaGENIE is an independent research interface, not an endorsed Google product. This interface modifies model outputs through null calibration, tissue grouping, statistical summaries and visualization. Predictions are not experimental measurements, diagnoses or evidence of pathogenicity.

The [AlphaGenome API terms](https://deepmind.google.com/science/alphagenome/terms) and [output terms](https://deepmind.google.com/science/alphagenome/output-terms) apply separately from this repository's code license. Review them before use or redistribution. The included output notice accompanies downloads. No claim of DeepMind approval for this distribution is made.

**Research preview / pre-release local package.** The dated validation record distinguishes live provider inference from offline tests and records the scope of native-platform checks. The September 11 study used the staged web inference path and GitHub aggregation; it did not execute a second complete API experiment through the local UI. Release tests run without provider calls. See [validation](docs/VALIDATION.md) and the current commit's GitHub Actions results.

The code license remains **owner decision pending; all rights reserved unless separately licensed**. Do not describe this as an open-source release. See [LICENSE](LICENSE), [NOTICE](NOTICE.md), and [publishing checklist](docs/PUBLISHING.md). These source files do not establish a completed GitHub release or public website deployment, and do not push or publish automatically.
