# M24-02 synthetic truth simulation generator

Status: provisional implementation; Scientific engineering owner review required.

M24-02 is the caller-declared synthetic truth and simulation boundary beneath
Batch/missing-protein sensitivity. It consumes a declared M24-01 sensitivity
artifact and locked generation configuration, then emits deterministic analytic
and semi-synthetic truth cases plus a reproducibility manifest. It does not
authenticate, traverse, mutate, or reinterpret upstream scientific content.

Authority is the permitted dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
slice `GLIO-PROTEOGEN_240_Module_Dossier.md:8360-8400`. The ABI remains
`0.1.0-provisional`; no frozen endpoint, catalogue, or production media type is
claimed. M24-01 is bound by caller-declared media type only; no unpublished
M24-01 service or runtime import is used.

Contract and safety boundaries:

- Normal, edge, missing, shifted, and adversarial fixture kinds, case IDs,
  seeds, representations, truth values, perturbations, manifest membership,
  configuration, and source artifacts are closed and deterministic.
- Seven caller-declared controls are checked fail-closed before generation.
  Denied, unsupported, malformed, or hostile inputs cannot become a negative
  finding or an inferred biological claim.
- Replay verifies canonical request digest, deterministic result identity,
  upstream digest binding, provenance module, and canonical result payload
  digest. The service and plugin share that replay path.
- FastAPI and Typer adapters parse once, sanitize validation failures, refuse
  output overwrite, and preserve the same canonical result bytes.
- KINOPHOS kinase-state ownership, generic all-omics fusion, treatment
  recommendation, identity/consent inference, upstream mutation, raw-content
  traversal, and biomarker-panel conclusions are prohibited.

Evidence is caller-declared and not issuer-authenticated. Synthetic fixture
uncertainty is explicitly not biological uncertainty; the result exposes all
seven uncertainty dimensions as not estimable and records support,
limitations, evidence, and control provenance.
