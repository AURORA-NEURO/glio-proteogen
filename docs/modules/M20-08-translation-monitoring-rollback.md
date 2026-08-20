# M20-08 translation monitoring and rollback

Status: provisional implementation; Bioinformatics owner review required.

M20-08 monitors caller-declared protein-subtype translation-health signals bound
to the published M20-07 downstream typed-export media type. It emits a typed
healthy, degraded, critical, or abstained result with an operational continue,
suspend, rollback, or abstain decision. The implementation does not traverse
raw upstream content or infer issuer authority.

Authority is dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
slice `GLIO-PROTEOGEN_240_Module_Dossier.md:7184-7224`. The ABI remains
`0.1.0-provisional`; no frozen catalogue, endpoint, or media contract is
claimed beyond the typed behavioral schema.

Safety boundaries:

- The request binds `application/vnd.glio-proteogen.m20-07+json` exactly and
  retains the upstream artifact reference.
- Usage telemetry, support drift, workflow effects, and discrepancies remain
  typed signals with explicit envelopes, evidence, and assessments.
- Non-evaluable signals abstain without a health report; drift never becomes an
  unsupported negative biological conclusion.
- Seven caller-declared controls are checked before signal traversal. Seven
  uncertainty dimensions, provenance, evidence, limitations, and human review
  are always explicit.
- No kinase activity, generic all-omics fusion, treatment recommendation,
  identity inference, or consent inference is emitted.
- Verification always regenerates the result from its bound request; disabling
  replay is rejected so a self-rehashed semantic finding cannot be accepted.

The engine, service, opaque plugin, FastAPI adapter, and Typer adapter share a
strict parse-once request path and canonical request/result replay verification.
The frozen evaluator executes eight scenarios and the adversarial contract and
interface suite covers tampering, control denial, unsupported input, malformed
JSON, media mismatch, duplicate closure, and no-overwrite behavior.
