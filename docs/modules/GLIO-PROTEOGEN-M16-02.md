# GLIO-PROTEOGEN-M16-02

## Cross-source alignment and reconciliation (provisional)

M16-02 is the reliability-aware alignment boundary beneath the KINOPHOS
object consumer. It binds caller-declared proteome, genome/transcriptome, and
PTM artifacts to a provisional M16-01 upstream result, then emits a typed
aligned evidence bundle and explicit discrepancy map. The implementation is
derived from dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, lines
5480-5520. The ABI remains `0.1.0-provisional` pending owner confirmation.

### Safety and scope

The runtime requires seven upstream controls: approved configuration, identity
lineage, provenance, consent, quality, support, and intended use. A failed or
missing control is rejected before model evaluation. The operation does not
infer kinase activity, treatment, identity, consent, mutation, or unsupported
negative findings. Unsupported, OOD, or not-evaluable inputs abstain without a
bundle; irreconcilable conflicts remain visible and require human review.

The locked dimensions are sample, time, territory, analyte, modality,
reference, and biological context. Each output includes typed measurement,
sampling, parameter, model-form, identification, support, and transport
uncertainty, plus provenance for all seven control decisions and every input
artifact.

### Interfaces

The strict plugin is exposed through `M1602Plugin` and `M1602Service`. FastAPI
routes are `/v1/m16-02/schema/{name}`, `/v1/modules/M16-02/reconcile`, and
`/v1/modules/M16-02/verify`. The Typer adapter provides `export-schema`,
`reconcile`, and `verify`. JSON inputs are parsed once, bounded, and validated
strictly; error responses are sanitized and CLI output refuses overwrites.

### Verification

`M1602AlignmentEngine.verify` checks the canonical result digest and can replay
the exact request. Release evidence covers aligned, warning, critical,
resolved, unsupported, prohibited, replay/tamper, authorization,
determinism, and uncertainty/provenance scenarios. The provisional benchmark
budgets are 2 seconds mean and 3 seconds p95 for ten calls.
