# M25-05 subgroup equity evaluator

## Authority and dependency boundary

M25-05 is a provisional Quality engineering/S3/G3 evaluator beneath the
`proteotype` parent. Its behavioral handoff is limited to dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
slice `GLIO-PROTEOGEN_240_Module_Dossier.md:8852-8892`. The declared upstream
is the caller-declared M25-04 evaluator media type. M25-04 has no frozen ABI or
published runtime in this lane, so this implementation binds only the media
string and imports no M25-04 symbols or payload.

## Contract and runtime

- strict contracts close all eight subgroup dimensions, metric/calibration/
  coverage identities, safety floors, nominal coverage targets, source-artifact
  uniqueness, request-context identity, and exact M25-04 media binding;
- deterministic execution reads only caller-declared typed metadata and emits
  no proteotype estimate, identity inference, treatment advice, kinase state,
  generic all-omics fusion, or unsupported-to-negative conclusion;
- seven-control preflight runs before declarations are evaluated; denied,
  limited, unsupported, non-calibrated, below-floor, malformed, or tampered
  cases remain explicit abstentions with review status;
- every result carries seven uncertainty dimensions, evidence, provenance,
  limitations, canonical request/result identities, and replay verification;
- FastAPI, Typer, and strict parse-once plugin paths share the same service.

## Evidence

The locked evaluator covers supported evaluation, safety-floor and coverage
abstention, calibration abstention, denied controls, deterministic reexecution,
replay, and tamper detection. The release evidence records the exact local
coverage, benchmark, fixture digests, package hashes, and independent verifier
results. ABI, owner confirmation, and the M25-04 upstream contract remain
provisional pending dossier governance.
