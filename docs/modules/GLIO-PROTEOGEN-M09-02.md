# GLIO-PROTEOGEN-M09-02 — representation and feature constructor

M09-02 owns the representation and feature-construction boundary beneath Complex stoichiometry.
It accepts content-addressed caller references for mass spectrometry, genome/transcriptome, PTM,
configuration, identity/lineage, provenance, consent, quality, support, and intended use, then
emits only a versioned complex-activity representation with complete feature lineage. The current
implementation is deterministic and replayable while the dossier leaves the ABI, feature
catalogue, estimator, endpoint, and media type provisional.

## Authority and boundary

- Authority: `GLIO-PROTEOGEN_240_Module_Dossier.md`, SHA-256
  `0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, lines 2960–3000.
- Owner/safety/gate: Computational biology / S2 / G1.
- ABI state: `0.1.0-provisional`; owner confirmation remains required before promotion.
- Parent target: `complex_activity`; `emits_parent` is explicitly false.
- Hard boundaries: no kinase activity, generic all-omics fusion, direct treatment recommendation,
  identity or consent inference, upstream mutation, evidence relabeling, or unsupported-to-negative
  conversion.

## Contract and runtime behavior

The strict request binds a provisional M09-01 formal-state result, unique feature specifications,
complete source and field lineage, ordered leakage-safe transformations, a locked representation
policy, and caller-declared source artifacts. Contract validators reject duplicate identifiers,
unbound lineage, malformed masks, failed leakage checks without affected held-out groups, and
feature/result closure violations. Canonical request and result digests bind replay to exact
content.

The runtime performs seven-control preflight before construction. Values are deterministic hash-
derived fixture values from the canonical request and content-addressed digests; no external
artifact is fetched or interpreted. Constructed features carry explicit masks, units, complete
lineage, evidence references, provenance, and seven explicit not-estimable uncertainty dimensions.
Missing, unsupported, OOD, not-evaluable, or leakage-failure markers abstain with no features and
an unsupported status; no negative biological finding is manufactured.

## Interfaces and evidence

FastAPI exposes strict schema, validate, and construct routes. Typer exposes `export-schema`,
`validate`, and `construct`, rejects existing output paths, and exits nonzero after writing an
abstention result. The plugin uses a parse-once weak validation token, preventing execution of an
unvalidated or digest-drifted request.

The release evidence includes contract/runtime/interface tests, executable construction and safe-
failure evaluation, deterministic benchmark output, authority-bound fixtures, traceability, and
package/import checks. These software gates do not authenticate evidence issuers, establish
biological truth, validate an estimator, demonstrate calibration or transportability, or authorize
clinical interpretation.
