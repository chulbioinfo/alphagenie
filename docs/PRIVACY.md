# Privacy and network behavior

## Statement for users

**AlphaGENIE Local does not collect API credentials for AlphaGENIE operators.** There is no operator credential endpoint, telemetry SDK, automatic feedback upload, user account registration or remote job proxy in this distribution. The supplied browser communicates with the server on your computer.

“Local” describes credential management, reference processing, job storage and visualization. **AlphaGenome inference is remote.** On an explicitly authorized run, your key authenticates API requests to Google DeepMind, and variant/interval information is sent to that service. This code cannot promise that Google does not log or retain data; the provider's own terms and policies apply.

## Data flow

| Action | Destination | Information |
|---|---|---|
| Open bundled results, track library, export PDF | Local browser ↔ local server | Bundled public data; no new API request |
| Enter key with CLI | Private local environment | Hidden terminal input → local credential file; or existing process environment |
| Validate a new variant | Local server, local FASTA/GTF, samtools | Submitted variant and target gene; no provider request |
| Run analysis | Google DeepMind AlphaGenome API | Key authentication metadata, real/null variants, requested intervals/output types |
| Save inputs/scores/logs | Private local jobs directory | Variant information, null designs, raw/adjusted scores, provenance, local file paths |
| Open an external citation/UCSC/terms link | User-selected website | Normal web-request metadata; UCSC links include the chosen genomic coordinates |
| Manually publish a GitHub issue | GitHub | Only the text/files you choose to submit; not automatic |
| Install Python dependencies | Official PyPI | Hash-verified wheel downloads; no AlphaGenome key is requested |
| Run the optional dependency advisory check / CI | Public OSV API | Public dependency names and versions only; no credentials, references or variant data |

The inspected SDK 0.8.0 uses TLS gRPC to `gdmscience.googleapis.com:443`, carrying the key in `x-goog-api-key` metadata. Endpoint behavior belongs to the upstream SDK and may change with future releases. The SDK is not vendored or firewalled by this application.

## Local storage and limits

- Default state: `~/.alphagenie/` (directory 700); `credentials.json` (file 600), `config.json`, `jobs.sqlite`, job inputs/results/logs. The directory must be user-owned and outside the checkout.
- File permissions restrict other ordinary OS users; they do **not** encrypt the key or protect it from your own processes, administrator/root, malware, process inspection, backups or sync software. Do not use a shared account.
- The environment-only key is not written to the credential file. It is available in memory/environment to the server/inference process and necessary scoring subprocesses. It is never passed as a command-line argument.
- Local non-inference subprocesses do not receive the API key. Operator/cloud/proxy environment variables are not propagated by default.
- No account, local login, password or recovery workflow is present. The browser receives a per-process request token for CSRF protection and key-present status, never the AlphaGenome credential value. The token is not local-user or local-program authentication.
- Other local programs or OS users able to reach the loopback listener may read private configuration/status, job lists/details and downloads or call local endpoints. Exact Host/Origin and request-token checks do not isolate them. Filesystem permissions do not restrict an unauthenticated HTTP response. Use only an owner-controlled private computer under a single trusted OS user; never use a shared server/account, tunnel, reverse proxy or public/LAN binding. Warnings are not access control.
- Known key values/Google-key patterns are redacted from application text logs, state messages and JSON writes. This is defense in depth, not proof against every future dependency error format. Do not publish raw logs or memory dumps without review.
- The application performs no automatic deletion of results. Use the key-delete command to remove the local credential file; remove/export your own job folders deliberately after reviewing contents. Provider copies and backups are outside the app's control.

## Before sharing

Do not commit your `.env`, private configuration, credentials, `.fa/.gtf` references, real patient/genomic inputs, SQLite DB, logs or personal jobs. `.gitignore` and the release scanner are safeguards, not a substitute for inspecting the staged diff. The provided source archive is built from a repository allowlist, never from the private state directory.
