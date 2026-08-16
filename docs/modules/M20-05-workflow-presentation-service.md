# M20-05 workflow presentation service

Status: provisional implementation; Platform engineering owner review required.

M20-05 is a deterministic workflow-presentation boundary beneath the biomarker
panel translation surface. It consumes one caller-declared M20-04 evidence
artifact and emits a bounded human-review workspace: task-specific views,
evidence summaries, uncertainty, discrepancies, provenance, and safe default
ordering remain explicit. The workspace never emits a protein-subtype conclusion.

Authority is the permitted dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
slice `GLIO-PROTEOGEN_240_Module_Dossier.md:7052-7092`. The ABI is explicitly
`0.1.0-provisional`; no frozen catalogue, endpoint, or media type is claimed
beyond this behavioral contract. The only upstream binding is the caller-
declared `application/vnd.glio-proteogen.m20-04+json` artifact. The service does
not import or traverse an M20-04 runtime service.

Safety boundaries:

- Seven caller-declared controls are checked fail-closed before review-item
  traversal: approved configuration, identity lineage, provenance, consent,
  quality, support, and intended use.
- Conflicted and unresolved items remain visible with explicit discrepancy and
  reviewer action. An abstained item produces an abstained workspace result;
  unsupported evidence is never converted into a negative claim.
- Seven uncertainty dimensions, source digests, control decisions, evidence,
  limitations, and human-review requirements are retained in every result.
- The module does not infer identity or consent, recommend treatment, traverse
  raw artifacts, perform kinase analysis, perform generic all-omics fusion, or
  relabel/erase upstream findings.

The service, strict parse-once plugin, FastAPI adapter, and Typer adapter share
one canonical request path. Request and result digests support replay and
tamper detection. The evaluator contains eight executable scenarios and the
adversarial suite covers denial, abstention, conflict preservation, malformed
inputs, interface parity, and digest tampering. Benchmark budgets are
provisional 500 ms mean and 750 ms p95.
