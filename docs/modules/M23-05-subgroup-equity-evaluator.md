# M23-05 subgroup equity evaluator

Status: provisional implementation; Bioinformatics owner review required.

M23-05 is the metadata-only subgroup performance, calibration, coverage, and
equity evaluation boundary beneath the variant-peptide parent. It consumes
caller-declared M23-04 media and emits an explicit evaluated report or safe
abstention. It does not fit a biological model, traverse scientific payloads,
infer identity or consent, or emit a parent variant-peptide conclusion.

Authority is the permitted dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
slice `GLIO-PROTEOGEN_240_Module_Dossier.md:8132-8172`. The ABI remains
`0.1.0-provisional`; no frozen endpoint, catalogue, or production media type
is claimed. M23-04 is an opaque caller-declared media boundary only; no
unpublished M23-04 service or runtime import is used.

Contract and safety boundaries:

- Eight required subgroup dimensions, finite performance bounds, calibration,
  canonical coverage arithmetic, safety floors, evidence, and locked
  configuration are explicit.
- Seven caller-declared controls are checked fail-closed before subgroup
  material is read. Unsupported, restricted, or non-evaluable material becomes
  an explicit abstention with human review required; it cannot become a
  negative finding.
- Replay verifies request digest, deterministic result identity, provenance,
  exact upstream artifact identity (ID, version, digest, and media type), and
  canonical result digest. Evaluated reports are also bound to the exact
  request performance, calibration, coverage, configuration, and version. The
  source manifest cannot substitute a
  same-ID upstream artifact with altered content or media metadata.
- The strict parse-once plugin, FastAPI adapter, Typer adapter, service,
  evaluator, and benchmark share one canonical request/result path.
- Kinase ownership, generic all-omics fusion, treatment recommendation,
  identity/consent inference, upstream mutation, raw content traversal, and
  parent conclusions are prohibited.
