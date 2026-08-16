# M13-07 — Plausibility and negative-control adjudicator

## Authority and status

- Dossier: `GLIO-PROTEOGEN_240_Module_Dossier.md`
- Dossier SHA-256: `0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`
- Authoritative slice: lines `4620–4663`
- Owner: Bioinformatics
- Safety class / gate: `S2 / G3`
- Parent target: `proteotype`
- ABI status: `0.1.0-provisional`; the dossier does not freeze endpoint names, schemas, media types, or implementation catalogue entries.

This implementation is intentionally provisional. It records the behavioral contract implied by the dossier and keeps owner confirmation pending instead of presenting inferred metadata as a frozen public ABI.

## Responsibility and boundary

The module owns plausibility and negative-control adjudication beneath the Variant-peptide channel. It accepts caller-declared orthogonal evidence, known negative controls, direction, conservation, assay-physics, and competing-mechanism controls, then emits only a plausibility grade and unresolved-conflict record. The parent output is `proteotype`; unresolved conflicts remain visible as conflict records.

The module does not own KINOPHOS kinase state, generic all-omics fusion, direct treatment recommendation, identity or consent inference, upstream mutation, evidence relabeling, or parent-output emission. Artifact references are content-addressed but opaque; this module never traverses their payloads or authenticates their issuer.

The dossier input boundary includes mass-spectrometry proteome, genome/transcriptome, PTM annotations, approved configuration, identity/lineage, provenance, consent, quality, support, and intended-use objects. The implementation keeps these as typed upstream references and never infers missing identity, consent, or evidence content.

## Contract and safety invariants

Every request is bound to the provisional M13-06 mechanism result media type, a non-empty source artifact set, all six required control kinds, and at least one known negative control. Control IDs are unique. The caller-declared outcome and observed direction are copied into exactly one evaluation per control; they cannot silently change during result assembly.

The adjudicated path requires six passed controls, no declared conflict, a supported decision, and a high plausibility grade. Failed, abstained, or non-evaluable controls produce no grade and a safe unsupported decision. A declared competing-mechanism conflict produces an abstained, review-required result with the mechanisms and evidence preserved. Unsupported evidence never becomes a negative finding.

The result binds the exact request digest and a canonical result digest. Provenance records all seven upstream controls and input digests. Measurement, sampling, parameter, model-form, identification, support, and transport uncertainty are explicit, with non-estimable dimensions on abstention. Human review is required for conflicts and blocking control outcomes.

The reference architecture is a curated rule, enrichment, or mechanistic baseline with a spatial proteotype field; advanced implementations may use a Bayesian graph, state-space, mechanistic, or foundation-assisted model, while the fallback is orthogonal-method consensus with negative-control gating and recurrence transition. All variants preserve the same contract, uncertainty, support, provenance, and abstention gates. Quality controls validate identity, version, units, completeness, assay support, and parent-specific quality; critical discrepancies, novel/OOD states, support overrides, claim promotion, release exceptions, and unresolved biological conflicts require human review.

## Runtime and interfaces

- `M1307PlausibilityEngine`: deterministic control evaluation, safe abstention, provenance, uncertainty, and replay verification.
- `M1307Service`: typed validation, execute, and replay seam.
- `M1307Plugin`: strict bounded JSON parse-once boundary with an opaque execution capability.
- `glio_proteogen.adapters.m1307.app`: standalone FastAPI routes for schema, adjudication, and replay verification.
- `glio_proteogen.adapters.m1307.m1307_app`: Typer commands for schema export, adjudication, and replay verification.

API and CLI failures are sanitized and do not echo submitted keys, values, or artifact payloads. CLI schema and result writes refuse to overwrite existing files.

## Verification evidence

The release matrix covers supported adjudication, failed and non-evaluable controls, unresolved conflict, denied upstream control, replay tamper, duplicate-key JSON, strict API/CLI parity, and hostile mapping/preflight cases. Evidence is recorded in:

- `release-evidence/m13_07/evaluation.json`
- `release-evidence/m13_07/benchmark.json`
- `release-evidence/m13_07/package.json`
- `docs/evidence/M13-07.md`
- `docs/traceability/M13-07.csv`

The reported release gates are scoped to the M13-07 contract, runtime, adapter, evaluator, and adversarial test surface; they are not a claim that the full dossier is complete.

