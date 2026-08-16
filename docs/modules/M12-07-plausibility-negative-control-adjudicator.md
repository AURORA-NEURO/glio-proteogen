# M12-07 — plausibility and negative-control adjudicator

## Authority and status

This implementation is grounded in dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
M12-07 lines 4260–4303. The dossier leaves the endpoint and media ABI
unfrozen, so all identifiers and media types in this document are explicitly
`0.1.0-provisional` and remain subject to owner confirmation.

Owner / safety / gate: Computational biology / S2 / G3. Parent output:
`biomarker_panel`. The module emits only a plausibility grade and unresolved
conflict record; it does not emit a biomarker panel, infer identity or consent,
perform generic all-omics fusion, infer kinase activity, or recommend treatment.

## Deterministic contract

`AdjudicateBiomarkerPanelPlausibilityRequest` binds a caller-declared
M12-06 mechanism artifact, source artifact references, six required control
kinds, immutable execution context and optional unresolved conflicts. The
contract enforces:

- strict operation/version/media identifiers and bounded collections;
- request/context identity equality and unique control/source/conflict IDs;
- exact one-to-one control evaluations in every result;
- complete result/request and result-payload SHA-256 digests;
- explicit `passed`, `failed`, `not_evaluable` and `abstained` outcomes;
- no conversion of missing or unsupported evidence into a negative finding;
- conflict preservation and human-review requirement on every abstained result;
- all seven shared uncertainty dimensions: measurement, sampling, parameter,
  model-form, identification, support and transport.

Opaque `ArtifactReference` values are never dereferenced or traversed. A
control is evaluable only when the caller explicitly declares an outcome.
Expected-direction disagreement is a hard failure. All failed, missing,
unsupported, or conflicting paths abstain without a plausibility grade.

## Runtime and interfaces

`M1207PlausibilityAdjudicatorEngine` performs seven-gate preflight, strict
round-trip validation, deterministic scoring, provenance construction and
replay verification. Six passed controls produce a high provisional grade;
any unresolved control or conflict produces a review-required abstention.

`M1207Service` is the application seam. `M1207Plugin` is a strict parse-once
capability boundary and binds execution tokens to the issuing plugin instance.
The standalone adapters expose:

- FastAPI `GET /v1/m12-07/schema/{name}`;
- FastAPI `POST /v1/modules/M12-07/adjudicate`;
- FastAPI `POST /v1/modules/M12-07/verify`;
- Typer `export-schema`, `adjudicate` and `verify` commands.

HTTP and CLI diagnostics are sanitized and never include submitted payload
values or traceback details. Schema export refuses overwrite.

## Evaluation and limitations

The locked fixture contains eight cases: supported high-grade, failed control,
missing observation, direction mismatch, unresolved conflict, denied quality
gate, explicit abstention, and replay/tamper. The evaluator must execute all
eight IDs in fixture order. The benchmark measures the complete public
adjudication operation and uses provisional 2-second mean / 3-second p95
budgets in nanoseconds.

This is a deterministic contract and safety integration baseline, not a
validated Bayesian graph or mechanistic biological estimator. Scientific model
family, calibration domain, assay reference set and owner-authenticated
evidence authority remain provisional pending the dossier's ABI freeze.
