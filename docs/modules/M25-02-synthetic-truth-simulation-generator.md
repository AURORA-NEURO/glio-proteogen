# M25-02 synthetic truth and simulation generator

Status: provisional implementation; Computational biology owner review required.

M25-02 is the caller-declared synthetic-truth and simulation boundary beneath
Uncertainty/stability/abstention. It consumes an M25-01 reference artifact and
locked generation configuration, then emits deterministic analytic and
semi-synthetic proteotype fixture cases plus a reproducibility manifest. It
does not authenticate source truth, traverse raw upstream content, or convert
simulation material into a biological conclusion.

Authority is the permitted dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
slice `GLIO-PROTEOGEN_240_Module_Dossier.md:8720-8760`. The ABI remains
`0.1.0-provisional`; no frozen endpoint, catalogue, or production media type
is claimed. M25-01 is bound by caller-declared media type only; no unpublished
M25-01 service or runtime import is used.

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
  recommendation, identity/consent inference, mutation/relabeling, raw-content
  traversal, and proteotype conclusions are prohibited.

Evidence is caller-declared and not issuer-authenticated. Synthetic fixture
uncertainty is explicitly not biological uncertainty; the result exposes all
seven uncertainty dimensions as not estimable and records support,
limitations, evidence, and control provenance.
