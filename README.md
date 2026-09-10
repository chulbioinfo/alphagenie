# AlphaGENIE Local

**AlphaGENome-Integrated Explorer** — v0.21 interface with the v0.20 RNA analysis engine.

Download this repository, run the interface on your own computer, and use **your own AlphaGenome API key**. No AlphaGENIE account or operator-hosted API proxy is involved.

> **Privacy:** This distribution contains no API key collection endpoint, telemetry or automatic feedback upload to AlphaGENIE. Keys stay in your local environment and are used to authenticate requests directly to Google DeepMind's AlphaGenome API. New inference sends variants/intervals and your key to Google; it is **not fully offline computation**. See [Privacy](docs/PRIVACY.md).

[Installation](docs/INSTALL.md) · [Methods](docs/METHODS.md) · [Development plan](docs/DEVELOPMENT_PLAN.md) · [Security](SECURITY.md)

## Quick start

Supported: **Python 3.11, macOS / Linux / WSL2**. Native Windows is not supported by the process/permission implementation. Node is only needed for developer tests.

```sh
bash scripts/setup.sh
source .venv/bin/activate
python -m alphagenie serve
```

Open **http://127.0.0.1:8877/**. Keep the terminal open; Ctrl+C stops the server and interrupts its active analysis. Saved examples work without an API key, genome references or a new API call. Use the exact numeric address, not `localhost`.

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
| UI | v0.21 | v0.21 local workspace |
| Numerical source | Frozen v0.20 release; 1,000 nulls each | Fresh inference using v0.20 engine code |
| Brain endpoint | Brain9: 8 adult categories + Embryo | Same versioned **Brain9** membership (8 adult + Embryo) |
| RNA curve | Frontal cortex, UBERON:0001870 | Same adult GTEx Brain_Cortex, polyA+, unstranded track |
| Multi-variant family | Fixed 17 variants, RGPD1 excluded | All requested variants must complete; first row is cosine reference |
| Network | None for local viewing/export | Google DeepMind API on explicit run |

Both workflows display **11 categories** for single variants: the nine Brain9 categories, Non-brain tissues, and Cells & cell lines. Only Brain9 enters primary statistics and cosine; multi-variant heatmaps show those nine categories, while the downloadable matrix retains all 11. The reviewed catalog has 371 tracks (14 adult brain + 7 embryonic brain + 153 non-brain tissue + 197 cells). New/missing tracks or changed classification metadata stop analysis for review; no guessed grouping or legacy fallback. See [Brain9 specification](docs/BRAIN9.md).

New RNA curves use the [exact v0.21 Frontal cortex selector](docs/RNA_CURVE.md), with no Whole brain, BA9, ENCODE or embryo fallback. All documentation, comments and interface text are in English. The legacy `README.ko.md` filename is only an English documentation redirect.

The SDK is pinned to **0.8.0**, not to an immutable provider checkpoint. New runs are **not guaranteed to reproduce September 2026 numbers**, and are not labeled as the frozen Brain9 analysis. No v0.18 numerical fallback is shipped or used. See the scientific limitations in [Methods](docs/METHODS.md).

Included: interactive saved-result dots, source-track search, stacked custom-dimension PDF export, original Figure 2/3/4 PDFs, saved null arrays/source tables, single/multi inference, matched-null generation, empirical statistics, BH/cosine, local job status and downloads. New-run figures currently use the original engine renderer; the configurable stacked exporter applies to saved single-variant results only.

## Repository layout

```text
alphagenie/       local CLI, private config, reference preflight, server, job runner
app/             read-only v0.21 explorer and saved-result rendering
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

**Pre-release local package.** Real-key end-to-end inference and clean-machine installation remain release gates; development tests use mocks and sealed data, without real API requests. The owner must choose the code license before announcing an open-source release. See [LICENSE](LICENSE), [NOTICE](NOTICE.md), and [publishing checklist](docs/PUBLISHING.md). No GitHub remote is embedded and nothing is pushed automatically.
