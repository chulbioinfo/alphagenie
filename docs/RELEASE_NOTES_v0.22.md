# AlphaGENIE 0.22.0 — research preview

Distribution **0.22.0** · interface **0.22** · scientific engine and manuscript data **0.20**.

## Changes

- Custom rendering/export now has single-render admission and a cache bounded to **32 MiB**, **12 entries** and a **five-minute TTL**. Request/body budgets and fail-fast busy responses prevent an unbounded custom-export queue; cached renders still recheck sealed source identity.
- A complete, SHA256-verified wheel lock preserves all 61 runtime versions, including AlphaGenome SDK 0.8.0. A separate installer lock pins pip 26.2.1 and setuptools 84.0.0. Setup uses a dedicated environment, refuses source builds and redirected install paths, then checks dependency consistency and the exact installed inventory.
- Dependency checks query public OSV advisories and fail on findings, incomplete results or network failure. CI uses the same locked setup on macOS/Linux arm64 and x86_64, with reviewed commit-SHA action pins. A workflow definition is not a claim of completed CI.
- Local request safeguards and private-computer warnings are reinforced. **No account, local login, password or recovery workflow is required.** The browser sees key-present status, never the AlphaGenome key value; no operator credential collection, telemetry or remote job proxy is added.
- English installation, privacy, security, architecture and validation documentation now distinguish package/interface versions from the preserved scientific lineage.

## Operating warning

Open `http://127.0.0.1:8877/` after running the local server. Use only your own trusted computer under one OS user. **Never run on a shared server/account, tunnel, reverse proxy or public/LAN listener.** Other local programs or OS users able to reach the port may call endpoints and read private status, jobs and outputs. Exact Host/Origin, CSRF tokens, request bounds and file permissions do not provide local-user authentication. A warning is not access control.

Your optional CLI key file remains owner-only **plaintext**, outside the repository. Environment-only key use is also supported. Explicit new inference sends key-authenticated variant/interval requests directly to Google DeepMind; it is not fully offline computation.

## Scientific continuity

No scientific runtime versions, statistical formulas, Brain9 membership, Frontal cortex selector, saved scores, 1,000-null arrays, source metadata or inference dates are changed by this release. Existing legacy jobs are not relabeled or reanalyzed. SDK pinning does not pin provider weights or guarantee reproduction of saved September 2026 numbers. No real provider inference is claimed.

## Validation and status

A fresh isolated macOS arm64 install passed `pip check` and the exact 63-package inventory. The final local regression run passed **108 Python tests and 8 Node tests**, with all **70 sealed assets** and **55 original downloads** preserved. Linux x86_64/aarch64 and macOS Intel passed hash-checked wheel-resolution dry runs, not native execution. Public OSV queries found no matches for the reviewed pins on 2026-09-10; this is not proof of safety. See the dated [validation record](VALIDATION.md).

Native CI, independent clean-machine validation and real eligible-key end-to-end inference remain stable-release gates. These notes do not establish that a GitHub release or public deployment has occurred. The code license remains **owner decision pending; all rights reserved unless separately licensed**. Provider/API/output terms and redistribution rights remain separate. See [LICENSE](../LICENSE), [NOTICE](../NOTICE.md), [Security](../SECURITY.md) and [Methods](METHODS.md).
