# GitHub development plan — v0.24 Local / v0.20 engine

Updated: 2026-09-11. Current research-preview package: **0.24.0**.

## Goal and scope

Provide a separately installable, single-user AlphaGENIE package with the v0.24
interface and v0.20 scientific tools. Credentials, local inputs and results are
not collected by AlphaGENIE operators. Distinguish immutable manuscript results
from newly submitted API analyses in the interface and provenance.

GitHub publication and public website deployment are separate release operations,
not effects of installation or tests. Copying production credentials/databases
and spending live API quota are not part of dependency or offline validation.
All distributed prose and code comments are in English; scientific symbols and
original biological identifiers are preserved.

## Design decisions

1. **One local repository:** plain HTML/CSS/JavaScript, FastAPI and Python workers.
   No frontend compilation is required; Node is used for developer tests.
2. **Terminal-only key entry:** hidden `getpass` input into an owner-only local
   file, or an environment variable. No web endpoint accepts or returns keys.
   Local file storage is not described as encrypted.
3. **Loopback-only service:** bind to 127.0.0.1, enforce exact Host/Origin and
   mutation tokens, and do not trust external CORS/proxies. No account, login,
   password or recovery workflow is used. Warnings are not access control:
   other local programs/users may call endpoints and read private status/jobs.
   Use only an owner-controlled private computer under one trusted OS user,
   never shared hosting, tunnels or a public/LAN listener.
4. **Private state:** configuration, SQLite jobs and outputs remain outside the
   source checkout. No operator account, cloud storage or remote deployment.
5. **Explicit, validated execution:** verify TSV syntax, REF, FAI, GTF, interval
   and SDK; require transmission consent; prevent duplicate concurrent inference.
   Interrupted jobs are not automatically retried.
6. **Reproducibility:** retain raw scores, null designs, output hashes and fresh
   inference timestamps/epochs. Require SDK 0.8.0 but record the provider
   checkpoint as unresolved, not as a pinned model.
7. **Reviewed dependencies:** hash-lock all 61 existing runtime versions and
   separately pin current reviewed pip/setuptools wheels. Exact inventories,
   fail-closed public advisory checks and SHA-pinned CI actions are required.

## Milestones and release gates

| Milestone | Status | Acceptance criteria or remaining work |
|---|---|---|
| Source isolation | Implemented | Required app, workers and six pipeline scripts; no production keys, databases or v0.18 numerical caches |
| Local security runner | Implemented | CLI/key management, preflight, consent, restricted child environment, redaction, locks and path validation |
| Interface integration | Implemented | Saved explorer, My analyses, status and downloads; no operator feedback upload |
| Brain9 adapter | Implemented; fresh-score reproduction verified | 19 staged-web fresh contexts, independent GitHub aggregation of those scores; all-null completeness, single 11-category display, nine-feature statistics |
| Frontal cortex curve | Implemented; recorded provider epoch verified | Exact adult GTEx Brain_Cortex track; RBFOX1/PTCHD1 curves reproduce within serialization precision |
| Tests/docs/packaging | Implemented; final integration recorded separately | Hash-locked install, offline scientific/security checks, English documentation, release scanner/source archive |
| Clean-machine/live-provider validation | Recorded study completed; validation scope remains bounded | Fixed-design 19-context provider run and separate GitHub aggregation passed; local UI was not used for a second provider experiment. Current native CI is checked per release commit |
| Redistribution permission | Owner decision required | Code license, contributor rights, manuscript data/output terms, repository owner/name |
| GitHub publication | Separate owner-authorized release operation | Actual push, CI and research-preview tag/release must be confirmed independently; source documentation does not prove them |

## Implemented scientific contracts

`worker/brain9.py` pins the metadata-only 371-track manuscript mapping by version
and SHA256: adult 8 categories (14 tracks), Embryo (7), Non-brain tissues (153)
and Cells & cell lines (197). Future catalog changes stop for review, rather
than forcing new data into old counts. A reviewed catalog extension requires a
new version.

Real/null metadata, track membership, finite values and every sampled null ID
must agree. Duplicate rows are collapsed per null and track before null
centering. Single plots have 11 categories; multi heatmaps, P/BH and cosine use
Brain9 only; downloadable matrices retain all 11. Earlier Brain6 jobs keep their
legacy labels.

`worker/rna_curve.py` selects the exact adult GTEx Brain_Cortex, UBERON:0001870,
polyA+ unstranded track used by the v0.21 saved explorer. It never substitutes
Whole brain, BA9, ENCODE or embryonic cortex. REF/ALT tracks are matched
independently by identity, not by a shared hardcoded channel index. Cache keys
include the full selection contract. Coordinate projection remains unchanged,
with raw arrays retained and inference provenance separate from rendering.
Old Whole brain artifacts are not renamed or reused as Frontal cortex.

No implementation step regenerates or changes the sealed manuscript scores,
1,000-null arrays or figures.

## Deferred features

- Shared v0.21 interactive point payloads and user-configurable stacked PDF
  export for newly generated jobs. Saved-result interactive exports already work;
  new jobs still use the existing local renderer.
- Optional OS keychain storage; separately validated controls for null seeds,
  taxonomy and model selection. Current seed: 20260527; provider model unresolved.
- Compressed raw-score storage and safe resume with provenance and quota review.
  No silent fallback to an old numerical cache.
- Broader catalog support only after metadata review and new regression tests.

## Reasons to withhold a stable release

Do not claim stable/public readiness while any of the following remains:
credential/private-path leakage, altered saved hashes, invalid null provenance,
confusion between legacy and new endpoints/curves, silent tissue/reference
fallback, reduced-family cohort statistics, missing real-key validation, or
unresolved licensing/redistribution rights.
