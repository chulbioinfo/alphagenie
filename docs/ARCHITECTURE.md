# Architecture

```text
Browser (127.0.0.1 only)
  ├─ Saved explorer → hash-bound release → local plotting/export (no inference)
  └─ My analyses → consent + local REF/GTF/SDK preflight
                    → private SQLite job record + inherited analysis lock
                    → isolated worker process
                         ├─ local matched-null generation / target QC
                         ├─ real + null score requests → Google DeepMind API
                         ├─ versioned Brain9 statistics / BH / cosine
                         └─ exact Frontal cortex prediction → local figure + source files
```

`alphagenie/config.py` owns state and key lifecycle. `validation.py` performs offline preflight. `server.py` provides the localhost boundary and saved/new routes; it does not expose the credential. `runner.py` creates fresh job identities and starts a separate process. The existing `worker`/`pipeline` handle scientific computation. `app/manuscript_release.py` verifies every saved asset against the sealed manifest; `manuscript_view.py` renders saved figures without modifying them.

No external database, remote storage, cloud authentication or operator feedback service is used. The local SQLite store is durable and outside the repository; browser state is presentation-only. The exact current production `app/main.py`, launch agents, tunnel settings and deployment scripts are intentionally excluded.

## Important boundaries

- Source code is portable; references, credential file and runtime jobs are user-specific and excluded from source archives.
- Saved data and fresh scores now share versioned Brain9 membership. `worker/brain9.py` reads only hash-bound classification metadata, never saved scores. New catalog drift fails closed. Old Brain6 local jobs keep their legacy labels; no migration or reanalysis is automatic.
- An input-only preset button never copies old scores into a new job.
- `worker/rna_curve.py` fixes the adult GTEx Brain_Cortex identity, matches REF/ALT channels independently and rejects incompatible caches. Old Whole brain artifacts remain untouched.
- All API jobs are fresh; loading/reformatting frozen outputs never touches the SDK client.
- Generated HTML from the old worker is not served. Generated files must resolve beneath the correct private job root.
- Raw score files are retained on disk but not exposed through an arbitrary path-download endpoint.
- Partial multi jobs preserve successful children but withhold cohort statistics. No reference replacement or family-size reduction is permitted through the local entry point.
