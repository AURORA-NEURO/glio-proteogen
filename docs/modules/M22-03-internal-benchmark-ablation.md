# M22-03 internal benchmark and ablation

Status: provisional implementation; Platform engineering owner review required.

M22-03 is the metadata-only internal benchmark and ablation boundary beneath
the protein-RNA discordance parent. It consumes a caller-declared M22-02
synthetic-truth artifact, a locked split, simple and mature baselines, explicit
ablations, and compute-matched comparisons. It emits benchmark evidence only;
it does not emit a protein-RNA discordance estimate or traverse scientific
payloads.

Authority is the permitted dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
slice `GLIO-PROTEOGEN_240_Module_Dossier.md:7684-7724`. The ABI remains
`0.1.0-provisional`; no frozen endpoint, catalogue, or production media type
is claimed. M22-02 is bound by caller-declared media type only.

Contract and safety boundaries:

- Locked split, simple/mature baseline closure, finite metrics, ablation
  deltas, compute matching, evidence, and dossier identifiers are explicit.
- Seven caller-declared controls are checked fail-closed before benchmark
  material is read. Denied, unsupported, malformed, or untrusted inputs do
  not become negative scientific findings.
- Replay verifies request digest, deterministic result identity, provenance,
  upstream digest binding, and canonical result digest.
- The strict parse-once plugin, FastAPI adapter, Typer adapter, service,
  evaluator, and benchmark share one canonical request/result path.
- KINOPHOS kinase-state ownership, generic all-omics fusion, treatment
  recommendation, identity/consent inference, upstream mutation, raw content
  traversal, and parent conclusions are prohibited.
