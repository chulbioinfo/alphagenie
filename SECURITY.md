# Security policy

This is a **single-user loopback application**, not a multi-user service or a hardened computation sandbox. Do not expose it via tunnels, a reverse proxy or a public interface. Only macOS/Linux/WSL2 are currently targeted.

Version 0.23 intentionally has **no account, local login, password or recovery workflow**. Run only on an owner-controlled private computer under a single trusted OS user. Never use a shared server or workstation account. Other local programs or OS users able to reach the loopback listener can call endpoints and may read private status, job details and downloads. Random job IDs and filesystem permissions do not turn those HTTP routes into authenticated access. A warning is not access control; no isolation against other local users is claimed.

The server enforces the exact `127.0.0.1:<port>` Host and local Origin, rejects cross-origin mutations, and uses a per-process local request token for browser CSRF protection. The token is not a user credential or local-program authentication barrier. The browser receives key-present status but never the AlphaGenome API key value. No web endpoint accepts or returns AlphaGenome API keys, and no operator credential collection is present. Optional CLI key storage is owner-only plaintext outside the checkout.

The server also disables trusted proxy headers and remote widgets, bounds request bodies and expensive analysis requests, and serves job artifacts only through job-relative allowlisted paths. Paths are based on random server-generated job IDs, not submitted names. These safeguards limit request and filesystem exposure; they do not provide a hostile multi-user sandbox or prevent same-account malware/administrator access.

API inference starts only after explicit consent and reference preflight. One inherited OS analysis lock covers the runner and scoring subprocesses. Graceful shutdown stops its own process group. After a hard crash, the old process may continue; the lock prevents a duplicate run. Do not bypass it by deleting lock files.

Installation uses exact hashed wheel locks, including reviewed pip/setuptools versions, in a dedicated virtual environment. CI checks the installed inventory and queries public OSV advisories for every locked package, failing on findings or an incomplete/unavailable response. Hashes and a clean advisory result are not proof that upstream code is safe. The OS, Python patch release, samtools and reference data require separate maintenance; see [installation](docs/INSTALL.md) and the dated [validation record](docs/VALIDATION.md).

To report a vulnerability, contact the repository maintainer privately through GitHub's private vulnerability reporting if enabled. Before publication, the owner must configure that channel. Do not post credentials, exploit details involving private data, real patient variants or unredacted logs publicly. No security email address is invented in this package.

If a real API key is exposed, revoke/rotate it at the provider immediately. Removing a file/commit does not undo disclosure. Local `key delete` cannot revoke a Google key or erase backups. Release scanners are heuristic, not a security guarantee.
