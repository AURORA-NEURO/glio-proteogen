# GLIO-PROTEOGEN-M07-04 — Probabilistic advanced estimator

## Authority and status

This is a deep provisional implementation of the permitted
`GLIO-PROTEOGEN_240_Module_Dossier.md` slice at lines **2328–2368**. The
authority SHA-256 is
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`.

The slice assigns M07-04 the probabilistic/mechanism-guided advanced estimator
under copy-number dosage/attenuation, with a parent proteotype target and G2
evidence expectations. The dossier describes responsibilities, inputs,
outputs, safety constraints, and uncertainty obligations; it does not freeze
the M07-02 representation symbols, operation name, schema catalogue, endpoint,
media type, or estimator implementation. This branch therefore uses
`0.1.0-provisional` and keeps every M07-04 ABI declaration explicitly
provisional.

## Contract boundary

The request binds caller-declared MS proteome, genome/transcriptome, PTM
annotations, M07-02 representation, approved configuration, identity/lineage,
provenance, consent, quality, support, and intended-use controls. References
are content-addressed and the configuration is required to point at the exact
representation artifact and media type. Observation IDs, evidence IDs,
source-artifact IDs, priors, estimates, and diagnostics are unique. Scalar,
interval, and categorical observations are closed as mutually exclusive typed
variants with finite numeric bounds.

The result carries typed posterior estimates, diagnostics, seven uncertainty
dimensions, support and human-review state, provenance, evidence, limitations,
request binding, and a canonical result digest. Validation closes the result
ID and request/result digest relationship so an apparently plausible but
rebound receipt cannot pass as a verified estimate.

## Runtime, safety, and replay

The runtime performs consent, identity/lineage, provenance, quality, support,
intended-use, and configuration preflight before estimator execution. The
current mechanism-guided implementation is a deterministic, locked declaration
proxy (`locked_declaration_proxy_v1`) intended to exercise the complete typed
and replayable boundary while owner-approved probabilistic model parameters
remain unfrozen. It projects finite scalar and interval observations only;
categorical observations and unfrozen learned families abstain with human
review required. Unsupported, missing, non-finite, ambiguous, or contradictory
inputs never become a negative finding.

The runtime emits no kinase activity, generic all-omics fusion, treatment
recommendation, identity inference, consent inference, or parent proteotype
result. `M0704Service.verify` validates the self digest and replays the exact
request. The plugin uses strict parse-once JSON, rejects duplicate keys and
non-finite values, and preserves service parity. Any changed request,
configuration, evidence, control state, or result is rejected or abstained.

## Interfaces and evidence

`adapters/m0704.py` exposes an isolated FastAPI app and Typer command group for
schema export, strict validation, estimation, and receipt verification.
Errors are sanitized and the repository-wide API remains untouched while the
ABI is provisional. `evals/m07_04` supplies deterministic fixtures, an
11-check evaluator, and a ten-iteration benchmark with provisional 2 s mean /
3 s p95 budgets. Release receipts bind evaluation, benchmark, coverage,
package/import smoke, fixture manifest, and traceability to the dossier digest.

The adversarial suite covers malformed transport, duplicate IDs, duplicate JSON
keys, invalid numeric shape, unauthorized controls, wrong upstream media type,
tampered replay, unsupported observations, API/CLI error parity, and mapping /
plugin parity. Coverage is branch-enabled and enforced at the repository's
95% release threshold.

## Limitations and promotion gate

This branch does not claim calibrated posterior accuracy, a validated clinical
or treatment use, a frozen learned estimator, or a frozen upstream M07-02 ABI.
Before promotion, the owner must freeze endpoint/media/schema identifiers,
provide mechanism-guided or learned model evidence, run uncertainty calibration
against the dossier's 85–95% acceptance expectation, and re-record the package
and benchmark receipts. Until then, safe abstention and deterministic replay
are the release criteria.

Rollback is to the prior M07-03/M07-02-compatible branch or to the last verified
M07-04 receipt. No persisted state or external content traversal is required;
removing this branch's provisional adapter and module paths restores the prior
runtime boundary.
