# GLIO-PROTEOGEN-M16-05

## Workflow presentation service (provisional)

M16-05 owns the human-review workspace beneath the KINOPHOS object consumer.
It presents task context, evidence summaries, uncertainty, discrepancies,
provenance, and next actions while preserving the parent target
`protein_rna_discordance`. It never owns kinase state, generic all-omics
fusion, or treatment recommendation. The implementation is derived from
dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, lines
`5612-5652`; the ABI remains `0.1.0-provisional` pending owner review.

Every request is gated by approved configuration, identity/lineage,
provenance, consent, quality, support, and intended use. The workspace has six
required views with deterministic safe ordering and automation decisions
disabled. Discrepancies are shown as warnings and remain reviewable; missing,
unsupported, OOD, or prohibited inputs abstain without a workspace and never
become negative findings.

All seven uncertainty dimensions and seven control decisions are emitted with
typed provenance. FastAPI routes are `/v1/m16-05/schema/{name}`,
`/v1/modules/M16-05/present`, and `/v1/modules/M16-05/verify`. The Typer
adapter provides `export-schema`, `present`, and `verify`; the plugin uses
strict parse-once capability tokens.
