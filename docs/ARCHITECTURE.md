# Architecture

```text
Browser (127.0.0.1 only)
  ├─ Saved explorer → hash-bound release → local plotting/export (no inference)
  └─ My analyses → local request token + consent + REF/GTF/SDK preflight
                    → private SQLite job record + inherited analysis lock
                    → isolated worker process
                         ├─ local matched-null generation / target QC
                         ├─ real + null score requests → Google DeepMind API
                         ├─ versioned Brain9 statistics / BH / cosine
                         └─ exact Frontal cortex prediction → local figure + source files
```

`alphagenie/config.py` owns state and key lifecycle. `validation.py` performs offline preflight. `server.py` provides the exact loopback boundary, per-process request token and saved/personal-job routes; it does not expose the API credential. `runner.py` creates fresh job identities and starts a separate process. The existing `worker`/`pipeline` handle scientific computation. `app/manuscript_release.py` verifies every saved asset against the sealed manifest; `manuscript_view.py` renders saved figures without modifying them.

No external database, remote storage, cloud authentication or operator feedback service is used. The local SQLite store is durable and outside the repository; the browser holds transient presentation state and a local request token, never the AlphaGenome key. The exact current production `app/main.py`, launch agents, tunnel settings and deployment scripts are intentionally excluded. Distribution/UI version 0.23 does not change the v0.20 scientific/data lineage or retained `v021` source paths.

## Private-computer trust boundary

There is no account, local login, password, personal-session cookie or recovery workflow. Exact numeric Host/Origin checks, a per-process local request token and JSON/body/request limits protect browser request handling; they are not local-user authentication. Status, job lists/details and output routes can be called by other programs or OS users able to reach the loopback listener. A random job ID and an owner-only directory do not make the HTTP route authenticated.

Use only an owner-controlled private computer under one trusted OS user, never a shared server/account, tunnel, reverse proxy or LAN/public service. Trust the browser and other local programs. Warnings are not access control, and this design claims no isolation from other local users, same-account malware or an administrator. API credential storage remains separate: terminal-only entry or the user's environment, without an operator-key collection endpoint. The browser receives key-present status, not the key.

## Dependency boundary

`scripts/setup.sh` creates a dedicated `.venv`. `install_dependencies.py` rejects redirected install paths, uses a hashed pip/setuptools bootstrap lock and the complete hashed runtime wheel lock, then requires `pip check` and an exact inventory. OSV checks are explicit dependency-metadata network requests, not scientific API calls. CI uses the same setup path on four platform families; a configured workflow is not evidence that those native jobs have run.

## Important boundaries

- Custom rendering admits one render at a time, fails busy requests promptly and caches at most 32 MiB/12 entries with a five-minute TTL. Request budgets prevent an unbounded custom-export queue; cached results still validate their sealed source identity.
- Source code is portable; references, credential file and runtime jobs are user-specific and excluded from source archives.
- Saved data and fresh scores now share versioned Brain9 membership. `worker/brain9.py` reads only hash-bound classification metadata, never saved scores. New catalog drift fails closed. Old Brain6 local jobs keep their legacy labels; no migration or reanalysis is automatic.
- An input-only preset button never copies old scores into a new job.
- `worker/rna_curve.py` fixes the adult GTEx Brain_Cortex identity, matches REF/ALT channels independently and rejects incompatible caches. Old Whole brain artifacts remain untouched.
- All API jobs are fresh; loading/reformatting frozen outputs never touches the SDK client.
- Generated HTML from the old worker is not served. Generated files must resolve beneath the correct private job root.
- Raw score files are retained on disk but not exposed through an arbitrary path-download endpoint.
- Partial multi jobs preserve successful children but withhold cohort statistics. No reference replacement or family-size reduction is permitted through the local entry point.
