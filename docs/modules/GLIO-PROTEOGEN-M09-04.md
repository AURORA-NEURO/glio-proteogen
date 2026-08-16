# GLIO-PROTEOGEN-M09-04 — probabilistic or advanced estimator

M09-04 owns the probabilistic or mechanism-guided primary estimator beneath Complex
stoichiometry. The implementation is deterministic and content-addressed while the dossier ABI,
model catalogue, posterior representation, and endpoint media types remain provisional. It emits
only a typed complex-activity posterior or an explicit abstention with diagnostics; it does not
emit a parent result.

## Authority and safety boundary

- Authority: `GLIO-PROTEOGEN_240_Module_Dossier.md`, SHA-256
  `0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, lines 3048–3091.
- Owner/safety/gate: ML engineering / S2 / G2.
- ABI state: `0.1.0-provisional`; owner confirmation is required before promotion.
- Inputs: caller-declared mass-spectrometry, genome/transcriptome, PTM, configuration,
  identity/lineage, provenance, consent, quality, support, and intended-use references.
- Outputs: primary posterior/estimate with optimisation diagnostics, typed uncertainty, support,
  provenance, evidence, and limitations, targeting `complex_activity` without emitting it.
- Hard boundaries: no KINOPHOS kinase-state ownership, generic all-omics fusion, direct treatment
  recommendation, identity/consent inference, upstream mutation, evidence relabeling, or
  unsupported-to-negative conversion.

## Contract and runtime behavior

The request binds a provisional M09-03 baseline artifact, an immutable configuration containing
objective, priors, constraints, optimizer, seed, iteration limit, and model reference, plus seven
caller-declared control decisions. Strict Pydantic contracts reject extras, coercion, duplicate
IDs, non-finite posterior/diagnostic values, malformed posterior shapes, and digest drift.

The reference runtime derives bounded deterministic fixture values from content-addressed hashes;
it does not claim those hashes are training data or a scientific model. Supported declarations
produce interval posteriors, a converged diagnostic, explicit seven-dimension uncertainty, and
provenance. Missing, unsupported, OOD, conflicted, review-required, or non-convergent declarations
produce no posterior and a typed safe abstention. Soft constraints remain visible as diagnostics.

## Interfaces and evidence

FastAPI exposes strict schema, validate, estimate, and replay-verification routes. Typer exposes
`export-schema`, `validate`, `estimate`, and `verify`; existing output paths are rejected and
abstention exits nonzero after writing canonical output. The plugin uses parse-once strict JSON and
a weakly held validation token, so callers cannot bypass validation or mutate the request.

Evidence includes adversarial contract/runtime/interface tests, supported/unsupported/OOD/
non-convergence evaluator scenarios, deterministic benchmark output, fixture authority, and
traceability. These software gates do not authenticate issuers, measurements, model accuracy,
calibration, transportability, or clinical utility.
