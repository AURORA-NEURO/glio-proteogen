# M25-08 evidence gate and release adjudicator

## Authority and dependency boundary

M25-08 is a provisional Platform engineering/S3/G5 gate beneath the
`proteotype` parent. The implementation is constrained to dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
slice `GLIO-PROTEOGEN_240_Module_Dossier.md:8984-9024`. Its ABI is
`0.1.0-provisional` and remains subject to owner confirmation.

M25-07 is bound through its declared media type as the upstream evidence
result. M25-06 is retained only as the exact media-only evidence boundary:
its runtime ABI is not imported or inferred in this lane.

## Contract and runtime

- strict schemas close traceability, risk controls, benchmark outcomes, claim
  ceilings, approvals, residual risk, post-release obligations, and signed
  release-record semantics;
- request identity, source-artifact identity, required upstream media, and
  M25-06 media-only retention are validated before adjudication;
- seven-control preflight runs before gate material is read; denial, malformed
  controls, missing evidence, failed benchmark, open critical risk, deferred
  approval, and tamper remain safe abstentions or rejections;
- deterministic results carry canonical request/result identities, seven
  uncertainty dimensions, provenance/control decisions, evidence, limits,
  human-review requirement, and mandatory semantic replay verification; a
  caller cannot disable replay or self-rehash a forged release payload;
- FastAPI, Typer, and the strict parse-once plugin expose the same service
  semantics with sanitized errors and no-overwrite output behavior.

## Evidence and release posture

The locked evaluator covers nominal adjudication, every blocking gate bucket,
denied controls, replay, self-rehashed release mutation rejection,
deterministic identity, and evidence/control closure.
The adversarial suite covers unknown keys, type coercion, media-boundary loss,
duplicate artifacts/findings/evidence, non-finite benchmarks, forged tokens,
strict duplicate JSON keys, identity mutation, and unsupported parent output.

This module adjudicates caller-declared release evidence. It does not infer
proteotype biology, identity, consent, kinase activity, generic all-omics
fusion, or treatment recommendations. A passing local gate is not owner
confirmation, cryptographic issuer authentication, or clinical authorization.
