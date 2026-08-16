# M22-01 reference-truth benchmark curator

Status: provisional implementation; Computational biology owner review required.

M22-01 is the signed reference-truth and benchmark-curation boundary beneath
Reference material. It consumes caller-declared M21-08 result media and a
closed set of reference entries, controls, challenge-set identifiers,
inclusions, and adjudications. It emits a locked curation package or an
explicit safe abstention with findings, support, provenance, evidence,
limitations, and seven uncertainty dimensions. It does not traverse or
interpret an unpublished upstream scientific payload.

Authority is the permitted dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
slice `GLIO-PROTEOGEN_240_Module_Dossier.md:7596-7636`. The ABI remains
`0.1.0-provisional`; no frozen endpoint, catalogue, or production media type
is claimed. The M21-08 dependency is bound by caller-declared media type only.

Contract and safety boundaries:

- Reference, control, challenge, inclusion, and adjudication identifiers are
  closed and unique. Positive/negative controls remain separate from
  reference entries, and challenge-set membership names known references.
- A request binds execution identity, the exact provisional M21-08 media,
  source artifacts, the upstream result, and all seven caller-declared
  controls. Missing, denied, or incompatible bindings fail closed.
- A fully reviewed package is locked by a canonical digest. Pending, rejected,
  incomplete, or inconsistent adjudications produce safe abstention and never
  a false benchmark truth finding.
- Replay verifies the request digest, deterministic result identifier, and
  canonical result digest. The strict parse-once plugin, FastAPI adapter,
  Typer adapter, service, evaluator, and benchmark share this path.
- Identity or consent inference, treatment recommendation, KINOPHOS kinase
  ownership, generic all-omics fusion, and raw upstream scientific-content
  traversal are prohibited.
