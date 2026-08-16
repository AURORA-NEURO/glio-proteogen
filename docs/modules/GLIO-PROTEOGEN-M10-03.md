# GLIO-PROTEOGEN-M10-03 — Mature baseline estimator

Authority: project-owner dossier SHA-256 `0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, lines 3364–3407.

This implementation is explicitly provisional (`0.1.0-provisional`) because the dossier does not freeze a public estimator catalogue, endpoint, or media convention. It provides a deterministic, caller-declared baseline under locked preprocessing and tuning. It never opens artifacts or infers protein-RNA discordance, kinase activity, fusion, treatment, identity, or consent.

The runtime requires all seven execution controls, emits family-declared scalar, interval, or categorical baseline estimates only for evaluable locked requests, and rejects unsupported controls before input traversal. Results carry seven uncertainty dimensions, diagnostics, provenance, evidence, limitations, and a canonical replay digest. Numeric values are finite-checked at the contract boundary.

The interface surface is provisional: `GET /v1/m10-03/schema/{name}`, `POST /v1/m10-03/validate`, `POST /v1/m10-03/estimate`, plus Typer `export-schema`, `validate`, and `estimate` commands.
