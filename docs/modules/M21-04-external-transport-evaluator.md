# M21-04 external transport evaluator

Status: provisional implementation; Platform engineering owner review required.

M21-04 evaluates caller-declared external transport of complex-activity
reference material across site, lab, platform, treatment-era, population,
disease-class, and specimen dimensions. It emits a typed transportability
report and support-domain update; it does not emit a complex-activity estimate.

Authority is dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
slice `GLIO-PROTEOGEN_240_Module_Dossier.md:7368-7408`. The ABI remains
`0.1.0-provisional`; no frozen catalogue, endpoint, or media contract is
claimed beyond the typed behavioral schema.

Safety boundaries:

- The request binds the exact `application/vnd.glio-proteogen.m21-03+json`
  benchmark media type and retains the upstream artifact reference.
- Independent validation, calibration floors, leakage-audit configuration,
  support-domain narrowing, provenance, and evidence remain explicit.
- Validation and evaluation dimensions must be unique and exactly equal the
  locked configuration; extra caller records cannot be silently carried into a
  report whose support-domain closure names a different set.
- A non-evaluable dimension or a fully narrowed domain abstains without a
  transport report; narrowed dimensions never become an unsupported negative.
- Seven caller-declared controls are checked before transport material is
  traversed. Seven uncertainty dimensions, limitations, and human review are
  always explicit.
- No complex-activity estimate, kinase activity, generic all-omics fusion,
  treatment recommendation, identity inference, or consent inference is
  emitted.

The engine, service, opaque plugin, FastAPI adapter, and Typer adapter share a
strict parse-once request path and canonical request/result replay verification.
The frozen evaluator executes eight scenarios; adversarial coverage includes
tampering, control denial, unsupported input, malformed JSON, media mismatch,
duplicate closure, abstention, and no-overwrite behavior.
