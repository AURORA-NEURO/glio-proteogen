# M11-07 — Plausibility and negative-control adjudicator

## Authority and status

- Dossier: `GLIO-PROTEOGEN_240_Module_Dossier.md`
- Dossier SHA-256: `0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`
- Authoritative slice: lines `3900–3943`
- Owner: Scientific engineering
- Safety class / gate: `S2 / G3`
- Parent target: `variant_peptide`
- ABI status: `0.1.0-provisional`; the dossier does not freeze endpoint names, schemas, media types, or implementation catalogue entries.

This implementation is intentionally provisional. It records the behavioral contract implied by the dossier and keeps owner confirmation pending instead of presenting inferred metadata as a frozen public ABI.

## Responsibility and boundary

The module adjudicates plausibility beneath protein-native subtype inference. It accepts caller-declared orthogonal evidence, known negative controls, direction, conservation, assay-physics, and competing-mechanism controls, then emits a plausibility grade only when every required control passes. Unresolved conflicts remain visible as conflict records.

The module does not own kinase activity, generic all-omics fusion, treatment recommendation, identity or consent inference, upstream mutation, evidence relabeling, or parent-output emission. Artifact references are content-addressed but opaque; this module never traverses their payloads or authenticates their issuer.

## Contract and safety invariants

Every request is bound to the provisional M11-04 mechanism result media type, a non-empty source artifact set, all six required control kinds, and at least one known negative control. Control IDs are unique. The caller-declared outcome and observed direction are copied into exactly one evaluation per control; they cannot silently change during result assembly.

The adjudicated path requires six passed controls, no declared conflict, a supported decision, and a high plausibility grade. Failed, abstained, or non-evaluable controls produce no grade and a safe unsupported decision. A declared competing-mechanism conflict produces an abstained, review-required result with the mechanisms and evidence preserved. Unsupported evidence never becomes a negative finding.

The result binds the exact request digest and a canonical result digest. Provenance records all seven upstream controls and input digests. Measurement, sampling, parameter, model-form, identification, support, and transport uncertainty are explicit, with non-estimable dimensions on abstention. Human review is required for conflicts and blocking control outcomes.

## Runtime and interfaces

- `M1107PlausibilityEngine`: deterministic control evaluation, safe abstention, provenance, uncertainty, and replay verification.
- `M1107Service`: typed validation, execute, and replay seam.
- `M1107Plugin`: strict bounded JSON parse-once boundary with an opaque execution capability.
- `glio_proteogen.adapters.m1107.app`: standalone FastAPI routes for schema, adjudication, and replay verification.
- `glio_proteogen.adapters.m1107.m1107_app`: Typer commands for schema export, adjudication, and replay verification.

API and CLI failures are sanitized and do not echo submitted keys, values, or artifact payloads. CLI schema and result writes refuse to overwrite existing files.

## Verification evidence

The release matrix covers supported adjudication, failed and non-evaluable controls, unresolved conflict, denied upstream control, replay tamper, duplicate-key JSON, strict API/CLI parity, and hostile mapping/preflight cases. Evidence is recorded in:

- `release-evidence/m11_07/evaluation.json`
- `release-evidence/m11_07/benchmark.json`
- `release-evidence/m11_07/package.json`
- `docs/evidence/M11-07.md`
- `docs/traceability/M11-07.csv`

The reported release gates are scoped to the M11-07 contract, runtime, adapter, evaluator, and adversarial test surface; they are not a claim that the full dossier is complete.
