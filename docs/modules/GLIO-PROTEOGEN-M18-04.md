# GLIO-PROTEOGEN-M18-04 — intended-use adapter

M18-04 converts caller-declared biomarker-panel evidence into a bounded intended-use-specific
object and policy decision beneath Spatial proteomics projection. It validates audience,
intended-use kind, evidence tier, claim ceiling and display semantics while preserving typed
support, provenance, uncertainty, evidence, limitations and review escalation. The ABI is
explicitly provisional because the dossier provides behavioral authority rather than a frozen
endpoint or media catalogue.

## Authority and boundary

| Property | Binding |
| --- | --- |
| Dossier SHA-256 | `0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181` |
| Exact slice | `GLIO-PROTEOGEN_240_Module_Dossier.md:6288-6328` |
| Owner / safety / gate | Quality engineering / S2 / G3 |
| Parent | `biomarker panel` context only; `emits_parent=false` |
| Operation / version | `adapt_biomarker_panel_intended_use` / `0.1.0-provisional` |
| Upstream boundary | Provisional M18-03 integrated-evidence artifact reference; content is never dereferenced |
| Primary / alternate / fallback | event-driven reliability orchestration / isoform-aware quantification / typed human review (declared; not executed) |
| Output ceiling | Intended-use object, policy decision, typed findings, support, uncertainty, provenance, evidence, limitations, or abstention |

M18-04 never performs KINOPHOS kinase-state work, generic all-omics fusion, treatment
recommendation, identity or consent inference, upstream mutation, relabeling, disagreement
erasure, or unsupported-to-negative conversion. Treatment, kinase, diagnosis and subtype claims
are blocked. Clinical and release uses remain review-required even when a bounded object is
adapted.

## Contract and runtime closure

- Seven caller-declared controls are preflighted before registration, claim, display or upstream
  traversal. Each is recorded in the seven-entry provenance record.
- Evidence tier and audience are checked against the declared intended use. Display must disclose
  support, uncertainty, provenance, evidence and limitations.
- Results are deterministic and replay-safe. The result identifier derives from the canonical
  request digest and payload tampering is rejected.
- Failed policy emits no adapted object and returns explicit abstention with unsupported support
  and human-review escalation. All seven uncertainty dimensions remain `not_estimable`.

FastAPI exposes `GET /v1/m18-04/schema/{name}`, `POST /v1/modules/M18-04/adapt`, and
`POST /v1/modules/M18-04/verify`. Typer exposes `export-schema`, `adapt`, and `verify`; JSON is
parsed once, validation errors are sanitized, and CLI outputs never overwrite existing files.
The plugin descriptor repeats the Quality engineering/S2/G3 authority ceiling.

The frozen evaluator covers allowed research, clinical review, unsupported audience, insufficient
tier, incomplete display, treatment/forbidden claims and replay tampering. Local evidence passes
8/8 adversarial cases (100%, target ≥95%). The benchmark is a software regression tripwire, not
scientific validation.
