# Security policy

This is a **single-user loopback application**, not a multi-user service or a hardened computation sandbox. Do not expose it via tunnels, a reverse proxy or a public interface. Only macOS/Linux/WSL2 are currently targeted.

The server enforces exact `127.0.0.1:<port>` Host and Origin, rejects cross-origin mutation, requires a per-process request token, disables trusted proxy headers and remote widgets, caps input size, and serves job artifacts only through job-relative allowlisted paths. Paths are based on random server-generated job IDs, not submitted names. Credentials are not part of the web API.

API inference starts only after explicit consent and reference preflight. One inherited OS analysis lock covers the runner and scoring subprocesses. Graceful shutdown stops its own process group. After a hard crash, the old process may continue; the lock prevents a duplicate run. Do not bypass it by deleting lock files.

To report a vulnerability, contact the repository maintainer privately through GitHub's private vulnerability reporting if enabled. Before publication, the owner must configure that channel. Do not post credentials, exploit details involving private data, real patient variants or unredacted logs publicly. No security email address is invented in this package.

If a real API key is exposed, revoke/rotate it at the provider immediately. Removing a file/commit does not undo disclosure. Local `key delete` cannot revoke a Google key or erase backups. Release scanners are heuristic, not a security guarantee.
