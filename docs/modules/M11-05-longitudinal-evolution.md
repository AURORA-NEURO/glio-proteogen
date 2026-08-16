# GLIO-PROTEOGEN-M11-05 — Longitudinal and evolutionary model

Status: `0.1.0-provisional` ABI, dossier-behavioral-brief-only. Authority is
the verified dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, lines
3812–3855. Owner: Data engineering. Safety: S2. Gate: G2.

## Scope and boundary

M11-05 consumes an opaque, caller-declared M11-04 mechanism/state reference,
mass-spectrometry and genomic/transcriptomic/PTM artifact references, ordered
time-point metadata, approved configuration, identity/lineage, provenance,
consent, quality, support and intended-use controls. It emits a time-indexed
trajectory and explicit change-point objects targeting the parent
`variant_peptide`. The module does not emit the parent output (`emits_parent`
is always false).

The reference implementation is a deterministic state-space baseline. It uses
only the explicit `territory` and `treatment_era` labels on each observation to
form state boundaries. Feature and upstream artifacts are content-addressed
references and are never traversed. This keeps the implementation auditable
while the dossier leaves the advanced Bayesian/graph/foundation ABI open.

The implementation does not infer identity or consent, mutate upstream
evidence, erase disagreement, convert unsupported evidence to a negative
finding, infer kinase activity, perform generic all-omics fusion, or recommend
treatment.

## Contract and runtime closure

- Eight strict JSON Schema 2020-12 exports carry explicit provisional metadata.
- Request binding requires the M11-04 media type, unique observations, strictly
  increasing sequence and aware timestamps, an ordered minimum history, locked
  configuration and future-leakage blocking.
- Results carry trajectory states, detected change points, diagnostics,
  support, all seven uncertainty dimensions, provenance, evidence, limitations,
  temporal/future-leakage flags and a canonical request/result digest pair.
- Seven control decisions are checked before observation or opaque-reference
  traversal; unauthorized calls fail closed.
- Replay verification validates both the result digest and deterministic
  reconstruction from the exact request.
- The plugin issues weak, request-bound validate-then-run tokens. FastAPI and
  Typer use strict JSON parsing, sanitized errors, no-overwrite output and the
  same service seam.

## Evidence and gates

The locked fixture contains eight evaluator cases spanning modeled transition,
no transition, denied control, temporal-order rejection, exact replay,
tampering, parent media binding and schema metadata. The final evaluator runs
8/8. The focused contract, runtime, evaluator and release-verifier suite runs
19 tests. Scoped branch coverage is
100% (506 statements, 72 branches), with a 95% fail-under threshold. The
10-iteration benchmark records a provisional mean budget of 2 seconds and p95
budget of 3 seconds; the measured evidence is in `release-evidence/m11_05`.

## Recovery and review

Any digest mismatch, temporal-order violation, unsupported control or malformed
wire payload is rejected without publishing a trajectory. A human review flag
remains set on modeled output because the ABI is provisional; owner review is
required before promotion, support override, novel/OOD state release or any
claim beyond the explicit caller labels.
