# M24-03 internal benchmark and ablation

Status: provisional implementation; Computational biology owner review required.

M24-03 is a metadata-only internal benchmark and ablation boundary beneath
the biomarker-panel parent. It accepts a caller-declared M24-02 synthetic-truth
artifact, a locked split, simple and mature baselines, explicit ablations, and
compute-matched comparisons. It emits benchmark evidence only. It does not
emit a biomarker-panel biological estimate or traverse scientific payloads.

Authority is the permitted dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
slice `GLIO-PROTEOGEN_240_Module_Dossier.md:8044-8084`. The ABI remains
`0.1.0-provisional`; no frozen endpoint, catalogue, or production media type
is claimed. M24-02 is bound by its caller-declared media type only: this lane
does not import or assume an M24-02 runtime service.

Contract and safety boundaries:

- Locked split, simple/mature baseline closure, finite metrics, ablation
  deltas, compute matching, evidence, and dossier identifiers are explicit.
- Seven caller-declared controls are checked fail-closed before benchmark
  material is read. Denied, unsupported, malformed, or not-evaluable inputs do
  not become negative scientific findings.
- Replay verifies request digest, deterministic result identity, provenance,
  upstream digest binding, and canonical result digest.
- The strict parse-once plugin, FastAPI adapter, Typer adapter, service,
  evaluator, and benchmark share one canonical request/result path.
- KINOPHOS kinase-state ownership, generic all-omics fusion, treatment
  recommendation, identity/consent inference, upstream mutation, raw content
  traversal, and parent conclusions are prohibited.


