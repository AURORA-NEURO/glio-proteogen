# M22-05 subgroup equity evaluator

Status: provisional implementation; Computational biology owner review required.

M22-05 is the metadata-only subgroup performance, calibration, coverage, and
equity evaluation boundary beneath the protein-RNA discordance parent. It
consumes caller-declared M22-04 evaluator material and emits an explicit
evaluated report or safe abstention. It does not fit a biological model,
traverse scientific payloads, or emit a parent discordance conclusion.

Authority is the permitted dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
slice `GLIO-PROTEOGEN_240_Module_Dossier.md:7772-7812`. The ABI remains
`0.1.0-provisional`; no frozen endpoint, catalogue, or production media type
is claimed. M22-04 is bound by caller-declared media type only.

Contract and safety boundaries:

- Eight required subgroup dimensions, finite performance bounds, calibration,
  coverage arithmetic, safety floors, evidence, and locked configuration are
  explicit.
- Seven caller-declared controls are checked fail-closed before subgroup
  material is read. Unsupported or non-evaluable coverage becomes an explicit
  abstention with human review required; it cannot become a negative finding.
- Replay verifies request digest, deterministic result identity, provenance,
  upstream digest binding, and canonical result digest.
- The strict parse-once plugin, FastAPI adapter, Typer adapter, service,
  evaluator, and benchmark share one canonical request/result path.
- KINOPHOS kinase-state ownership, generic all-omics fusion, treatment
  recommendation, identity/consent inference, upstream mutation, raw content
  traversal, and parent conclusions are prohibited.
