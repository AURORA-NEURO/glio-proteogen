# M22-02 synthetic-truth simulation generator

Status: provisional implementation; Computational biology owner review required.

M22-02 is the caller-declared synthetic-truth generation boundary beneath
Orthogonal immunoassay validation. It consumes a declared M22-01 reference
truth artifact and locked generation configuration, then emits a deterministic
synthetic-truth corpus and manifest for the protein-RNA discordance parent. It
does not authenticate or traverse upstream scientific payloads.

Authority is the permitted dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
slice `GLIO-PROTEOGEN_240_Module_Dossier.md:7640-7680`. The ABI remains
`0.1.0-provisional`; no frozen endpoint, catalogue, or production media type
is claimed. M22-01 is bound by caller-declared media type only.

Contract and safety boundaries:

- Fixture kinds, case identifiers, seeds, representations, truth values,
  perturbations, manifest membership, configuration, and source artifacts are
  closed and deterministic.
- Seven caller-declared controls are checked fail-closed before generation.
  Unsupported, denied, or malformed inputs cannot become a negative finding.
- Replay verifies request digest, deterministic result identity, provenance
  module, upstream digest binding, and canonical result digest.
- The strict parse-once plugin, FastAPI adapter, Typer adapter, service,
  evaluator, and benchmark share one canonical request/result path.
- KINOPHOS kinase-state ownership, generic all-omics fusion, treatment
  recommendation, identity/consent inference, upstream mutation, raw content
  traversal, and parent protein-RNA discordance conclusions are prohibited.
