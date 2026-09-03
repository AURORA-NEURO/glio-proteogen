# GLIO-PROTEOGEN-M10-05 — mechanism and constraint integrator

This lane implements the M10-05 dossier slice (authority lines 3452–3495;
dossier SHA-256 `0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`).
The public operation, media type, and schema catalogue remain explicitly
provisional because the dossier freezes behavior but not an ABI.

## Behavior

The runtime performs a seven-control authorization preflight before reading
constraint or feature inputs. The compatibility vocabulary remains available:
`always_true`/`true`/`satisfied` produce a satisfied outcome and
`always_false`/`false`/`violated` produce a violated outcome. Requests may also
declare bounded feature observations (`observed`, `left_censored`, `missing`, or
`unsupported`). Numeric comparisons such as `feature.pathway >= 0.5` are then
evaluated against the measured value with an assay-error-scaled residual and a
continuous Gaussian satisfaction strength. Left-censored evidence is used only
when its bound proves an upper constraint; missing or unsupported evidence remains
`not_evaluable` and is never made negative. Other caller expressions safely
abstain.

Hard constraints cannot carry weights and a hard violation always produces a
review-required abstention. Soft constraints require an explicit weight and
always emit an ablation record; measured soft conflicts retain a quality-weighted
effect rather than collapsing to a binary proxy and mark the result for review.
Every result binds the exact request digest, result ID, all evaluations, all soft
ablations, seven uncertainty dimensions, ordered provenance controls, evidence,
limitations, and a rederived result digest.

The module does not emit kinase activity, generic all-omics fusion, treatment
recommendations, identity/consent inference, upstream mutations, relabeling,
disagreement erasure, or unsupported-to-negative findings.

## Interfaces

- FastAPI: `GET /v1/m10-05/schema/{contract}`, `POST /v1/m10-05/validate`,
  `POST /v1/m10-05/integrate`, and `POST /v1/m10-05/verify`.
- Typer app `m1005_app`: `export-schema`, `validate`, `integrate`, and `verify`.
- Library: `M1005Service`, `M1005ConstraintEngine`, and issued
  `ValidatedM1005Request` plugin tokens.

All JSON ingress uses duplicate-key rejection, a byte ceiling, canonical
normalization, and one strict model parse. Plugin execution requires an issued
weak-reference token bound to the original request object and canonical digest.

## Gate evidence

The locked local evidence includes focused contract/runtime/interface tests,
a nine-case evaluator matrix, deterministic benchmark samples, schema
serialization, strict Ruff and MyPy checks, and an isolated package import.
The package evidence records wheel/sdist hashes, byte sizes, member inventories,
and the clean isolated import. Generated coverage and package directories are
task-local and removed after the final audit.
