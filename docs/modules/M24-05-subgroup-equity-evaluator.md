# M24-05 subgroup equity evaluator

Status: provisional implementation; ML engineering owner review required.

M24-05 is the caller-declared subgroup performance, calibration, coverage, and
equity boundary beneath Batch/missing-protein sensitivity. It consumes a
declared M24-04 external-transport evaluator result through media type only and
evaluates eight required subgroup dimensions: age, sex, ancestry, subtype, site,
low-resource, pediatric/AYA, and rare biological state.

Authority is the permitted dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
slice `GLIO-PROTEOGEN_240_Module_Dossier.md:8492-8532`. The ABI remains
`0.1.0-provisional`; no frozen endpoint, catalogue, or production media type is
claimed. M24-04 is unpublished and therefore remains a caller-declared media
boundary; this module imports no M24-04 runtime service or implementation.

Contract and safety boundaries:

- Locked configuration requires all eight subgroup dimensions, performance,
  calibration, and coverage closure. Bounds, floors, fractions, source IDs,
  context request IDs, and upstream media are validated before evaluation.
- Seven caller-declared controls are checked fail-closed before traversing
  subgroup material. Safety-floor breaches, unsupported/not-evaluable coverage,
  rare-context limited coverage, and calibration abstention produce explicit
  review-required results without a report.
- Replay verifies canonical request digest, deterministic result identity,
  upstream digest binding, provenance module, finding uniqueness, and canonical
  result payload digest.
- FastAPI and Typer adapters parse once, sanitize validation failures, refuse
  output overwrite, preserve canonical result bytes, and return nonzero for
  explicit abstention.
- KINOPHOS kinase-state ownership, generic all-omics fusion, treatment
  recommendation, identity/consent inference, unsupported-to-negative
  conversion, upstream mutation, raw-content traversal, and biomarker-panel
  conclusions are prohibited.

Evidence is caller-declared and not issuer-authenticated. The result exposes
all seven uncertainty dimensions as not estimable and records support,
limitations, evidence, control provenance, findings, and human-review state.
