# AlphaGENIE 0.23.0 — research preview

Distribution **0.23.0** · interface **0.23** · scientific engine and manuscript data **0.20**.

## Corrections

- Read native matched-null design `null_variant_id` and compatible `null_id` columns. Require exact agreement when both exist and reject missing, blank, duplicate or conflicting IDs. Preserve identifier strings through score loading and exports, including leading zeros and literal `NA` tokens.
- Keep the original sampled design byte-identical. Retain exact design/scored ID membership, requested null count, complete track coverage, finite-score and Brain9 metadata checks. Ten-null smoke tests are supported; the defect was not a 1,000-null minimum.
- Register the combined cohort null-consensus file for local downloads only when every child supplies its export. Incomplete/stale exports are not advertised. Failed-child cohorts still withhold cohort statistics.
- Extend offline regressions for deletion, insertion and substitution designs, compatible aliases, malformed IDs, preserved source files, complete null exports and downstream result delivery.
- Align local and public interface version labels with v0.23. Public saved-result viewing remains separate from local fresh analysis; public new inference stays disabled.

## Scientific and privacy continuity

No inference algorithm, null sampling, statistical formula, Brain9 membership,
Frontal cortex selector, dependency version, sealed manuscript value or historical
inference date is changed. Existing failed jobs are not automatically rewritten,
resubmitted or relabeled. Re-submitting starts a new provider run and may consume
quota; see [controlled offline recovery](NULL_ID_COMPATIBILITY.md).

The release verification does not use a real API credential or make new
AlphaGenome calls. Offline replay of already-scored data is not fresh inference;
an unavailable cortex curve is not invented or replaced with an older prediction.

## Personal-computer research preview

No account or login is required. Use a private computer under one trusted OS
user; do not expose the local port, use a tunnel, or run on shared accounts or
servers. Other local programs/users can reach the unauthenticated local service.
Browser request safeguards are not local-user isolation.

AlphaGENIE operators do not collect your API key. Optional terminal-entered key
storage is owner-only plaintext outside the repository. Explicit new analysis
authenticates directly to Google DeepMind using your key. This release contains
no private runtime state or credentials.

See [Validation](VALIDATION.md), [Installation](INSTALL.md), [Security](../SECURITY.md)
and [Methods](METHODS.md). This remains a research preview, not a clinical or
multi-user product. Provider eligibility, real-key end-to-end validation and
licensing/redistribution approvals remain separate. The code license is unchanged:
all rights reserved unless separately licensed.
