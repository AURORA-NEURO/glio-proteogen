# M10-04 — Probabilistic or advanced estimator

Status: deep-build complete locally; operation, posterior representation,
endpoint, media catalogue, and model catalogue remain provisional pending owner
confirmation.

Authority: `GLIO-PROTEOGEN_240_Module_Dossier.md`, SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, lines
3408–3451.

## Responsibility and boundary

M10-04 owns the probabilistic or mechanism-guided estimator beneath Pathway /
proteotype factors. Its provisional request binds an M10-03 baseline artifact,
mass-spectrometry proteome, genome/transcriptome, PTM annotations, approved
configuration, identity/lineage, provenance, consent, quality, support, and
intended-use decisions as immutable references. The implementation does not
traverse caller payloads.

The estimator must not own kinase state, generic all-omics fusion, treatment
recommendation, mutation of upstream evidence, relabeling, identity or consent
inference, or conversion of unsupported evidence into a negative. It emits no
parent protein–RNA discordance claim in this provisional lane.

## Deterministic safety behavior

All seven caller controls are preflighted before strict model validation. Any
unresolved state fails closed. Metadata-only requests retain the historical
explicit abstention with a `not_evaluable` optimization diagnostic, seven
`not_estimable` uncertainty dimensions, evidence references, limitations, and
required human review. Requests that include bounded measured observations
resolved to finite Normal priors now execute a deterministic robust Normal
posterior fit: quality/error precision, Huber IRLS outlier resistance, damped
updates, 95% posterior intervals, objective trace diagnostics, and exact replay.
Unsupported prior families or unresolved observation IDs abstain rather than
being silently coerced into a score.

Requests and result payloads use canonical SHA-256 digests. Verification checks
the request digest, result payload digest, and exact request replay. The plugin
uses a sealed parse-once token. FastAPI and Typer share duplicate-key,
non-finite-number, byte-limit, and sanitized-validation behavior.

## Evidence and release gates

The fixture manifest binds the exact dossier digest and line slice. Contract,
runtime, API/CLI, adversarial, evaluator, benchmark, coverage, and package
receipts are under `release-evidence/m10_04`. The provisional benchmark uses a
2-second mean and 3-second p95 budget until the owner supplies a frozen
performance contract. Measured posteriors remain research-use-only and do not
promote a parent clinical or treatment claim.
