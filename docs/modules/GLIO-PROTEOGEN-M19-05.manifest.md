# GLIO-PROTEOGEN-M19-05 module manifest

| Property | Locked value |
| --- | --- |
| Module | GLIO-PROTEOGEN-M19-05 |
| Title | Workflow presentation service |
| Component | C19 Immunopeptidomic evidence |
| Responsibility | Deterministic task-specific human-review workspace presentation over the exact caller-declared M19-04 evidence bundle |
| Owner | Data engineering |
| Version | 0.1.0-provisional |
| Safety class | S2 |
| Evidence gate | G4 |
| Operation | present_proteotype_human_review_workspace |
| Inputs | M19-04 aligned evidence bundle; mass-spectrometry proteome, genome/transcriptome, PTM, configuration, identity/lineage, provenance, consent, quality, support and intended-use metadata |
| Output ceiling | Human-review workspace only, with typed findings, support, seven uncertainty dimensions, provenance, evidence, limitations and next actions |
| Views | evidence_review, uncertainty, discrepancy, provenance, support, task_summary |
| Parent target | proteotype |
| Runtime model | Stateless deterministic schema-first presentation with authorization-first preflight and safe abstention |
| API | GET /v1/m19-05/schema/{name}; POST /v1/modules/M19-05/present; POST /v1/modules/M19-05/verify |
| CLI | glio-proteogen-m19-05 export-schema NAME; glio-proteogen-m19-05 present REQUEST; glio-proteogen-m19-05 verify RESULT |
| Capacity | Six ordered views; one item per view; bounded source/evidence references; request cap inherited from strict JSON boundary |
| Claims ceiling | Human-review organization of caller-declared evidence; no identity, consent, kinase, treatment, generic all-omics, or biological truth claim |
| Dossier source | Authoritative dossier SHA-256 0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181, lines 6692-6732 |

## Data and model manifest

All fixtures are synthetic, non-clinical metadata. The service does not open external scientific
files, call a registry, access an object store, or execute a learned model. It preserves the full
aligned bundle and source references as typed opaque evidence. The reference architecture is a
typed service-oriented integration; event-driven orchestration and semi-supervised or latent-class
alternatives are recorded as declared-not-executed options.

The result exposes measurement, sampling, parameter, model-form, identification, support and
transport uncertainty as explicit not-estimable dimensions. It never converts missing,
unsupported, conflicted or abstained input into a negative finding. Critical discrepancy,
novel/OOD state, support override, claim promotion, release exception and unresolved conflict
remain human-review work.

## Safety and replay invariants

- Seven authorization controls are checked before traversal: identity, consent, provenance,
  quality, support, intended use and upstream compatibility.
- M19-04 media type and exact aligned bundle are required; source artifact identity and digest
  bindings are retained without relabeling, deduplication or mutation.
- The six views are a closed set with contiguous positions and one item per view. Safe default
  ordering is deterministic and review-visible.
- Result identity is derived from the canonical request digest. Canonical result bytes bind the
  request, workspace, findings, support, uncertainty, provenance, evidence and limitations.
- Provenance input identity binds every emitted evidence reference, including policy and all
  seven authorization-control evidence artifacts.
- Replay verifies request identity, result identity, payload digest and exact workspace/source
  closure. Tampering raises a typed replay error and never yields a partially trusted result.
- The service, FastAPI adapter, Typer CLI and strict parse-once plugin share the same schema and
  canonical execution semantics. Errors are sanitized and output paths are no-overwrite.

## Review, recovery and qualification

This module cannot self-approve. A governed release record must identify an externally
authenticated reviewer, decision, timestamp, exact schema/result digests, fixture and benchmark
reports, provenance and consent evidence, and any support override or claim-promotion decision.
Abstention is the safe result for failed controls, unsupported upstream state, missing required
evidence, or unresolved critical discrepancy. Recovery is append-only: retain the immutable
request/result/evidence package, correct the external source, submit a new request, and replay
the complete locked corpus. No prior result is overwritten, deleted, relabeled or silently
promoted.
