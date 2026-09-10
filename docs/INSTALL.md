# Installation and operation

## Requirements

- Python **3.11**; a separate virtual environment. `hashlib.file_digest` and POSIX process/file-permission controls are used.
- macOS or Linux; Windows users use WSL2 with files in the Linux filesystem. Native Windows is unsupported. Only the current development environment has been tested so far.
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

`setup.sh` downloads dependencies from pip's configured package source; it does not request an API key. `requirements.txt` pins direct dependencies. `requirements-lock.txt` records the full tested macOS/Python 3.11 package-version snapshot; it is not a cross-platform, hash-locked dependency resolution. To try the exact snapshot, install it into a separate Python 3.11 venv and run `pip check`. Do not silently upgrade the SDK: preflight rejects versions other than 0.8.0.

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

Open **http://127.0.0.1:8877/#local**. Five required TSV columns:

```text
gene_symbol	chrom	pos1	ref	alt
RBFOX1	chr16	6018925	TCCG	T
```

`variant_group_id` is optional and must be unique. Unknown columns are rejected. Supported lengths: 16,384 / 131,072 / 524,288 / 1,048,576 bp. Supports A/C/G/T SNV/MNV and simple left-anchored insertions/deletions, not symbolic alleles, mitochondrial variants or complex delins.

Click **Check references** for a local-only check. To infer, select transmission consent and click **Run with my API key**. The server always validates again. A 10-null job is useful for a credential/installation smoke test only; use 1,000 or more for manuscript-depth testing. Sampling/coverage can still fail even at 1,000 requested nulls. This is reported, not replaced with old data.

One active analysis is allowed per private state directory. Multi-variant jobs run children sequentially and only produce cohort BH/cosine if **all requested variants succeed**. The first input row is the intended cosine reference. Successful child outputs survive a later failure. A new submission always creates a fresh job; it is not an automatic resume.

## Outputs and stopping

Browser downloads list result figures, source tables, null summary/design, QC and provenance where produced. Full raw real/null TSVs and sidecars remain under `~/.alphagenie/jobs/<job-id>/`. No broad file-browser or upload-to-operator endpoint exists.

Ctrl+C in the server terminal stops that server's active process group. Already sent remote requests cannot be recalled. An abrupt OS kill/crash can leave an inference worker alive; the inherited analysis lock prevents a second overlapping run. Restart the server to inspect status and wait for it to finish. Do not delete lock/state files to bypass this safeguard while a worker may still be alive. No automatic retry is performed. A lost worker is marked interrupted only when no analysis lock remains held.

Do not expose the port through a reverse proxy, tunnel, LAN binding or shared-host service. The private edition is not the approved operating model for a public API proxy.
