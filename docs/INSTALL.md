# Installation and operation

## Requirements

- Python **3.11**; a separate virtual environment. `hashlib.file_digest` and POSIX process/file-permission controls are used.
- macOS 12+ (Apple Silicon or Intel), or Linux with glibc 2.28+ (x86_64 or aarch64). Windows users use a supported WSL2 Linux distribution with files in the Linux filesystem. Native Windows, Alpine/musl and other platforms are unsupported by the wheel lock. Local execution is verified on macOS; the CI matrix checks all four listed platform families when it runs.
- `samtools` on PATH for fresh inference, plus a local GRCh38 primary-chromosome FASTA with matching `.fai`, and GENCODE v46 annotation GTF (plain or gzip).
- Disk space for references and all real/null scores. 1 Mb × 1,000 nulls × many variants can be very large because raw scores include all returned genes. No hard runtime/storage estimate is promised; test one small job first.
- Your own eligible AlphaGenome API account/key and applicable provider terms. No bundled key and no server weights are supplied.

## Install

Clone/download the repository and enter its root, then:

```sh
bash scripts/setup.sh
source .venv/bin/activate
python -m alphagenie doctor
python -m alphagenie serve
```

If your Python 3.11 executable has a different name:

```sh
ALPHAGENIE_PYTHON=/path/to/python3.11 bash scripts/setup.sh
```

`setup.sh` installs into this checkout's dedicated `.venv`; it does not modify a global Python environment or request an API key. It downloads only hash-verified wheels from official PyPI, disables pip configuration/environment overrides for the install, and refuses source builds. A trusted CPython 3.11 installation and its bundled `ensurepip` are the bootstrap trust boundary. Keep your Python patch release current through your trusted Python distributor.

### Dependency reproducibility and security

`requirements.txt` records reviewed direct dependencies, not the install command. `requirements-lock.txt` pins the complete 61-package runtime inventory with SHA256 hashes for the supported CPython 3.11 wheel platforms. The existing runtime versions are preserved, including `alphagenome==0.8.0`. `requirements-installer.txt` separately pins `pip==26.2.1` and `setuptools==84.0.0`, replacing the vulnerable installer versions found in the release audit. These installer wheels were reviewed against [official pip](https://pypi.org/project/pip/26.2.1/) and [setuptools](https://pypi.org/project/setuptools/84.0.0/) metadata on 2026-09-10.

Installation first installs the hashed installer lock, then the hashed runtime lock without resolving unlisted dependencies, then runs `pip check` and an exact installed-package inventory check. The flags follow [pip's secure-install guidance](https://pip.pypa.io/en/stable/topics/secure-installs/). Extra or mismatched packages make verification fail; the script never deletes an existing environment. For an older or customized `.venv`, stop any server, move that environment aside, and rerun setup to create a fresh one. Do not silently upgrade the SDK: preflight rejects versions other than 0.8.0.

To check the current environment and public advisories:

```sh
python scripts/dependency_check.py --installed
python scripts/dependency_check.py --advisories
```

The advisory command and CI query [OSV](https://google.github.io/osv.dev/post-v1-querybatch/) with public package names/versions only. Any match, incomplete response or network failure fails the check; no credentials, reference paths or scientific data are submitted. An empty result is not proof of safety, and future advisories can make a previously passing build fail. CI installs this same lock on macOS arm64/Intel and Linux arm64/x86_64 and pins its third-party actions to reviewed commit SHAs.

Maintainers can run `python scripts/refresh_dependency_lock.py` to compare wheel hashes with official PyPI metadata. `--write` refreshes hashes for the existing pins only; it is not a dependency resolver or permission to upgrade. Review every pin/hash change and rerun fresh-install, inventory, advisory and offline scientific tests on the supported platforms. Hashes prevent unnoticed artifact substitution after review; they do not establish that upstream code is safe. The lock does not pin the OS, Python patch release, samtools or external reference data.

## Private computer only

Open `http://127.0.0.1:8877/` after starting the server. No account, local login, password, cookie sign-in or recovery workflow is required. Use the exact numeric loopback address and chosen port, not `localhost`.

Use only your own trusted computer under a single OS user. **Never run this on a shared server, shared workstation account, tunnel, reverse proxy or LAN/public listener.** The local API has no user-authentication boundary. Other local programs or OS users able to connect to the port may call endpoints and read private configuration/status, job lists and outputs. Filesystem permissions protect direct file access, not an unauthenticated loopback HTTP route. A warning does not provide access control.

Exact Host/Origin checks, a per-process request token and request bounds provide browser-CSRF and input-handling safeguards, not isolation against local users or programs. The browser sees whether an AlphaGenome key is configured, never the key value. Keep the OS account, browser and local software trusted; stop the server when it is not needed. Ctrl+C stops the server and interrupts its active analysis. See [security limits](../SECURITY.md).

## Reference files

Obtain GRCh38 from [UCSC hg38 downloads](https://hgdownload.soe.ucsc.edu/goldenPath/hg38/bigZips/) and the matched annotation from [GENCODE human release 46](https://www.gencodegenes.org/human/release_46.html). References are not bundled or downloaded automatically. Use UCSC-style `chr1`…`chr22`, `chrX`, `chrY` names and forward-strand VCF alleles.

Install samtools through your trusted OS/conda package manager, then index your FASTA:

```sh
samtools faidx /path/to/hg38.fa
python -m alphagenie configure --fasta /path/to/hg38.fa --gtf /path/to/gencode.v46.annotation.gtf.gz
```

Use `--samtools /absolute/path/to/samtools` if it is not on PATH. Keep references outside the repository. Record source URL, release, retrieval date and SHA256 for your references; score provenance records annotation path/stat identity, not an automatic full-genome SHA. Changing a reference between runs changes reproducibility. REF and annotation overlap are rechecked before each job, but those checks alone cannot certify a whole reference release.

## Key management

```sh
python -m alphagenie key set
python -m alphagenie key status
python -m alphagenie key delete
```

Only `key set` reads a key, using a hidden interactive prompt. It stores an owner-only **plaintext** credential file outside Git. `status` reports presence, not authentication; it does not contact Google. `delete` removes that one credential file, not backups or environment variables. For no disk persistence, supply `ALPHA_GENOME_API_KEY` through your shell/secret manager without recording it in history. Environment credentials take precedence over the local file and must exist when the server starts. Do not use `.env` files in the repository.

Default private state is `~/.alphagenie/`. `ALPHAGENIE_HOME` can select another dedicated, user-owned directory **outside the repository**. Do not select a shared, network-synced or publicly served directory. The service is single-user, not protected from other processes under your own OS account.

## Analysis

Open **My analyses** at `http://127.0.0.1:8877/#local`; no login is needed. Five required TSV columns:

```text
gene_symbol	chrom	pos1	ref	alt
RBFOX1	chr16	6018925	TCCG	T
```

`variant_group_id` is optional and must be unique. Unknown columns are rejected. Supported lengths: 16,384 / 131,072 / 524,288 / 1,048,576 bp. Supports A/C/G/T SNV/MNV and simple left-anchored insertions/deletions, not symbolic alleles, mitochondrial variants or complex delins.

Click **Check references** for a local-only check. To infer, select transmission consent and click **Run with my API key**. The server always validates again. A 10-null job is useful for a credential/installation smoke test only; use 1,000 or more for manuscript-depth testing. Sampling/coverage can still fail even at 1,000 requested nulls. This is reported, not replaced with old data.

One active analysis is allowed per private state directory. Multi-variant jobs run children sequentially and only produce cohort BH/cosine if **all requested variants succeed**. The first input row is the intended cosine reference. Successful child outputs survive a later failure. A new submission always creates a fresh job; it is not an automatic resume.

## Outputs and stopping

New analyses use the strict manuscript Brain9/11-category mapping described in
[BRAIN9.md](BRAIN9.md). If provider metadata or track membership changes, inspect
`classification_audit.json` / `.tsv` in the failed job's private `results/`
directory. Do not bypass this error by relabeling tracks or substituting old
scores. Classification receipts are also downloadable for successful jobs.

New RNA curves select the exact adult GTEx Brain_Cortex (Frontal cortex,
UBERON:0001870) polyA+ unstranded track. If unavailable or ambiguous, the curve
is marked unavailable; existing scores remain valid and no other tissue is
substituted. See [RNA_CURVE.md](RNA_CURVE.md).

When upgrading from a 0.21 local release, stop the old server first, replace the source
checkout with 0.22.0, install its reviewed dependency locks in a dedicated environment,
and restart from the new checkout. No account or session migration is needed. Keep your private
state directory. Existing Brain6 jobs and Whole brain curves remain legacy; no automatic
conversion, relabeling or new API run occurs.

Browser downloads list result figures, source tables, null summary/design, QC and provenance where produced. Full raw real/null TSVs and sidecars remain under `~/.alphagenie/jobs/<job-id>/`. No broad file-browser or upload-to-operator endpoint exists.

Ctrl+C in the server terminal stops that server's active process group. Already sent remote requests cannot be recalled. An abrupt OS kill/crash can leave an inference worker alive; the inherited analysis lock prevents a second overlapping run. Restart the server to inspect status and wait for it to finish. Do not delete lock/state files to bypass this safeguard while a worker may still be alive. No automatic retry is performed. A lost worker is marked interrupted only when no analysis lock remains held.

Do not expose the port through a reverse proxy, tunnel, LAN binding or shared-host service. The private edition is not the approved operating model for a public API proxy.
