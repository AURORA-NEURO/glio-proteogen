# M21-07 human-factors and operational evaluator

Status: provisional implementation; Bioinformatics owner review required.

M21-07 evaluates caller-declared human-factors and operational material across
reviewer comprehension, automation bias, throughput, latency, downtime,
recovery, and fallback dimensions. It emits a typed operational report and
findings; it does not emit a complex-activity estimate.

Authority is dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
slice `GLIO-PROTEOGEN_240_Module_Dossier.md:7500-7540`. The ABI remains
`0.1.0-provisional`; no frozen catalogue, endpoint, or media contract is
claimed beyond the typed behavioral schema.

Safety boundaries:

- The request binds the exact `application/vnd.glio-proteogen.m21-06+json`
  challenge result and retains the upstream artifact reference.
- Reviewer comprehension, automation-bias, throughput, latency, downtime,
  recovery, and fallback material remain typed, caller-declared, and supported
  by explicit evidence.
- A non-evaluable operational dimension abstains without a report; failure is
  visible as an operational finding and never becomes a biological negative.
- Seven caller-declared controls are checked before operational material is
  traversed. Seven uncertainty dimensions, limitations, provenance, evidence,
  and human review are always explicit.
- No complex-activity estimate, kinase activity, generic all-omics fusion,
  treatment recommendation, identity inference, or consent inference is
  emitted.

The engine, service, opaque plugin, FastAPI adapter, and Typer adapter share a
strict parse-once request path. Replay validates the envelope, regenerates the
operational result from its bound request, and compares the complete canonical
result; a self-rehashed digest is not accepted as evaluator provenance.
The frozen evaluator executes eight scenarios; adversarial coverage includes
surface/report/support/provenance/evidence/limitation/request tampering, control
denial, unsupported input, malformed JSON, media mismatch, duplicate closure,
abstention, and no-overwrite behavior.
