# GLIO-PROTEOGEN-M08-08 — evidence and explanation publisher

M08-08 owns the evidence and explanation publisher beneath the C08 transcript–protein
discordance workflow. It records input attribution, diagnostics, assumptions, counter-evidence,
uncertainty, limitations, provenance, and reconstruction material. The implementation publishes
only a versioned evidence bundle and explanation object; it does not emit a parent `protein_subtype`
claim.

## Authority and safety boundary

- Authority: `GLIO-PROTEOGEN_240_Module_Dossier.md`, SHA-256
  `0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, lines 2864–2907.
- Owner/safety/gate: Data engineering / S2 / G3.
- ABI state: `0.1.0-provisional`; catalogue, symbols, endpoint details, and claim-promotion policy
  require owner confirmation before promotion.
- Hard boundaries: no KINOPHOS kinase state, generic all-omics fusion, direct treatment
  recommendation, identity or consent inference, upstream mutation, evidence relabeling, or
  unsupported-to-negative conversion.

## Contract and runtime behavior

The request binds caller-declared M08-07 calibration and M08-06 uncertainty artifacts, source
artifacts, an evidence bundle, and seven immutable control decisions. Strict Pydantic contracts
reject extras and coercion, enforce request/context identity, upstream media types, unique source
identifiers, closed assumption and reconstruction links, explicit counter-evidence, deterministic
result identifiers, and replay-verification closure.

Preflight requires granted consent, resolved identity/lineage, and accepted configuration,
provenance, quality, support, and intended-use controls. The runtime never fetches or mutates
external content. It projects source and upstream references by digest, emits explicit limitations
and non-estimable publisher uncertainty, and preserves counter-evidence. Unsupported, missing,
OOD, or quarantined markers abstain without an evidence bundle or explanation and use
`review_required` support status.

Results are canonical JSON. Replay verifies both canonical bytes and the result payload digest;
tampered, malformed, oversized, and non-canonical inputs fail closed. The plugin uses a parse-once,
weakly held validation token so callers cannot bypass validation or mutate the validated request.

## Interfaces and evidence

The isolated FastAPI surface exposes strict schema, validate, and publish routes. Typer exposes
`export-schema`, `validate`, and `publish`; existing output paths are rejected and abstentions exit
nonzero after writing the canonical result. The executable evaluator covers supported publication,
safe unsupported abstention, replay, tamper rejection, counter-evidence, reconstruction, and
determinism. The benchmark measures ten deterministic publication calls against 2e9/3e9 ns
provisional mean/p95 budgets.

The release record includes focused contract/runtime/interface/evaluator tests, branch coverage,
strict Ruff/MyPy/compile gates, fixture authority binding, traceability, and package import
evidence. Passing software gates are not biological validation, issuer authentication, calibration,
transportability, clinical utility, or owner approval for ABI promotion.
