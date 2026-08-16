# M09-06 — uncertainty decomposition engine

## Authority and provisional status

This implementation is traced to GLIO-PROTEOGEN-M09-06, dossier lines
3136–3179, at dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`.
The dossier defines the seven uncertainty dimensions, a nominal 90% coverage
envelope of 85–95%, safe abstention, and the complex-activity parent boundary.
It does not freeze the estimator catalogue, endpoint, media type, or M09-05
handoff ABI. All public symbols are therefore `0.1.0-provisional` and require
owner confirmation before production use.

## Responsibility and boundaries

M09-06 consumes caller-declared M09-05 integrator evidence, mass-spectrometry,
genome/transcriptome, PTM, configuration, identity, provenance, consent,
quality, support, and intended-use references. It emits a typed seven-component
uncertainty decomposition, a sensitivity envelope, support, provenance,
evidence, and limitations for the parent target `complex_activity`.

The module never fetches or mutates referenced content. It does not own kinase
activity, generic all-omics fusion, or direct treatment recommendation; it does
not infer identity or consent, erase disagreement, or convert missing or
unsupported evidence into a negative finding. `emits_parent` is permanently
false in the provisional result contract.

## Runtime guarantees

- Strict immutable Pydantic contracts require measurement, sampling, parameter,
  model-form, identification, support, and transport exactly once.
- Every component exposes an explicit `UncertaintyEstimate`; no missing
  dimension is represented as zero or hidden in a residual bucket.
- Evaluated sensitivity requires finite ordered bounds and observed coverage in
  the declared 0.85–0.95 gate around nominal 0.90.
- Seven upstream controls are checked before estimator policy evaluation.
- Unsupported, non-evaluable, missing, or uncalibrated declarations abstain;
  calibration uncertainty requests review rather than producing a claim.
- Result and request digests bind canonical JSON bytes. Replay verifies the
  typed result, request digest, result digest, and byte determinism.
- FastAPI, Typer, and the sealed plugin use the same service boundary and do not
  traverse external content.

## Verification

The release evidence records the focused contract/runtime/interface/evaluator
tests, adversarial safe-failure cases, strict lint and typing gates, scoped
coverage, evaluator matrix, deterministic benchmark, and package/import checks.
The ABI, estimator and benchmark budgets remain provisional pending owner and
reviewer sign-off.
