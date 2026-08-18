# M25-07 human-factors and operational evaluator

## Authority and dependency boundary

M25-07 is a provisional Data engineering/S3/G4 evaluator beneath the
`proteotype` parent. Its behavioral handoff is limited to dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
slice `GLIO-PROTEOGEN_240_Module_Dossier.md:8940-8980`. The declared upstream
is the caller-declared M25-06 robustness-challenge media type. M25-06 has no
frozen ABI or published runtime in this lane, so this implementation binds only
the media string and imports no M25-06 symbols or payload.

## Contract and runtime

- strict contracts close all seven operational dimensions, target/tolerance
  semantics, fallback availability, mandatory downtime/recovery/fallback
  paths, source-artifact uniqueness, request-context identity, and exact
  M25-06 media binding;
- deterministic execution reads only caller-declared typed metadata and emits
  no proteotype estimate, identity inference, treatment advice, kinase state,
  generic all-omics fusion, or unsupported-to-negative conclusion;
- seven-control preflight runs before declarations are evaluated; denied,
  failing, unavailable, malformed, or tampered cases remain explicit
  abstentions with human review required;
- every result carries seven uncertainty dimensions, evidence, provenance,
  limitations, canonical request/result identities, and replay verification;
- FastAPI, Typer, and strict parse-once plugin paths share the same service.

## Evidence

The locked evaluator covers supported evaluation, metric and fallback
abstention, unavailable fallback, denied controls, deterministic reexecution,
replay, dimension closure, and tamper detection. Release evidence records exact
local coverage, benchmark, fixture digests, package hashes, and independent
verifier results. ABI, owner confirmation, and the M25-06 upstream contract
remain provisional pending dossier governance.
