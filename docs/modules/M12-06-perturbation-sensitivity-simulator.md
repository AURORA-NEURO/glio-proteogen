# M12-06 — perturbation and sensitivity simulator

Status: **provisional implementation** (`0.1.0-provisional`). Authority is the
M12-06 dossier slice at lines 4216–4259, SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`.

## Responsibility and boundary

M12-06 owns bounded in-silico perturbations, parameter sweeps, alternative
priors, assay perturbations, and mechanism stress tests beneath the
Driver-to-protein consequence map. It emits only a sensitivity surface and
bounded perturbation response for the parent target `biomarker_panel`.

It does not own KINOPHOS kinase activity, generic all-omics fusion, treatment
recommendation, identity or consent inference, upstream mutation, disagreement
erasure, or conversion of unsupported evidence into a negative finding. The
upstream consequence artifact is content-addressed and intentionally opaque.

## Implemented behavior

- Strict frozen Pydantic contracts with provisional ABI metadata and eight JSON
  Schema 2020-12 exports.
- Caller-declared seven-control preflight: approved configuration, identity /
  lineage, provenance, consent, quality, support, and intended use.
- Deterministic bounded reference simulation. Baseline and perturbed values
  must remain inside the configured response envelope.
- Unsupported scenarios, out-of-envelope values, and denied controls abstain;
  abstention emits no sensitivity surface and requires human review.
- Seven uncertainty dimensions are always present. Simulated results expose
  declared support-quality indicators; abstentions use explicit
  `not_estimable` states.
- Canonical request/result digests, deterministic IDs, immutable provenance,
  evidence links, replay verification, and tamper rejection.
- Standalone FastAPI and Typer adapters use strict JSON duplicate-key and
  finite-number rejection, sanitized diagnostics, and no-overwrite output.

## Evidence and gates

The executable fixture contains six cases: supported bounded simulation,
unsupported perturbation abstention, out-of-envelope abstention, and three
control-denial cases. The evaluator also performs exact replay. The final
focused lane contains 33 tests, Ruff and strict MyPy pass, and scoped
branch-enabled coverage is recorded in `release-evidence/m12_06/evaluation.json`.

The benchmark times only the public service execution over ten iterations and
checks provisional mean / p95 budgets of 2,000,000,000 / 3,000,000,000 ns.
Package evidence records wheel and sdist hashes, member counts, and isolated
wheel import verification.

## Traceability

| Dossier requirement | Implementation evidence |
| --- | --- |
| Sensitivity surface and bounded response | `contracts/m12_06/v1.py`, runtime `engine.py` |
| Support envelope and safe abstention | `engine.py`, `test_m12_06_runtime.py` |
| Seven uncertainty dimensions | `engine.py::_uncertainty` |
| Identity, consent, quality and provenance controls | `engine.py::preflight_m1206_authorization` |
| Replay, tamper, and deterministic output | `contracts/m12_06/canonical.py`, `verify_m1206_result` |
| Locked tests and benchmark | `evals/m12_06`, `tests/fixtures/m12_06`, release evidence |
