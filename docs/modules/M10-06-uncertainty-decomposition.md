# M10-06 — Uncertainty decomposition engine

Status: deep-build complete locally; operation, endpoint, media catalogue,
decomposition representation, and model catalogue remain provisional pending
owner confirmation.

Authority: `GLIO-PROTEOGEN_240_Module_Dossier.md`, SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, lines
3496–3539.

## Responsibility and boundary

M10-06 owns typed uncertainty decomposition beneath Pathway/proteotype factors:
measurement, sampling, parameter, model-form, identification, support, and
transport. It binds an opaque M10-05 constraint-integrator result, a locked
policy, and caller-declared proteome/transcriptome/PTM references. It emits a
typed uncertainty object and sensitivity envelope for the parent target
`protein_rna_discordance`.

Kinase state, generic all-omics fusion, direct treatment recommendation,
upstream evidence mutation, relabeling, identity/consent inference, and
unsupported-to-negative conversion are outside the boundary. Source payloads
are never traversed or copied into the result.

## Deterministic safety behavior

The seven controls (approved configuration, identity/lineage, provenance,
consent, quality, support, and intended use) are preflighted before strict
validation. Unresolved controls fail closed. Until calibration, nominal 90%
coverage, sensitivity, transport, and benchmark evidence are owner-locked,
the runtime returns an explicit abstention with seven `not_estimable`
uncertainty dimensions, an abstained sensitivity envelope, calibration and
sensitivity findings, evidence, limitations, and required human review.

The evaluated envelope is structurally constrained to nominal 90% coverage and
an observed 85–95% gate. Requests and results use canonical SHA-256 digests;
verification replays the exact embedded request. FastAPI, Typer, and the plugin
share strict duplicate-key/non-finite JSON handling and sanitized errors.

## Release evidence

The fixture manifest binds the exact dossier digest and line slice. Contract,
runtime, interface, evaluator, benchmark, coverage, traceability, and package
receipts are under `release-evidence/m10_06`. All ABI and endpoint details are
explicitly provisional until the Data engineering owner confirms them.
