# M22-07 replay-integrity evidence

## Scope

M22-07 remains a provisional, caller-declared human-factors and operational
evaluator. This hardening does not authenticate M22-06 material, traverse raw
scientific content, infer protein-RNA discordance, or expand the module's
claim ceiling.

## Defect closed

The former replay path checked request identity, request digest, and result
payload digest before revalidating the result envelope. Those checks prove
internal consistency only. A caller able to edit a contract-valid nested
report, finding, evidence, or provenance record could recompute the outer
`result_digest` and pass replay.

## Replay contract

Replay now performs ordered closure checks and semantic regeneration:

1. Direct request-digest, result-identifier, and result-digest checks retain
   their precise existing errors for forged envelopes.
2. The result is strictly re-parsed and the deterministic evaluator regenerates
   the complete result from its bound request.
3. The full canonical JSON model is compared; any difference fails closed as
   a replay error.

The same semantic check is used through the service, strict plugin, FastAPI
`/v1/modules/M22-07/verify` route, and Typer `verify` command. Interfaces
continue to expose sanitized errors.

## Adversarial coverage

The focused suite includes contract-valid self-rehashed mutations of a report
metric, fallback path, and provenance activity through service/plugin seams,
plus FastAPI and Typer parity. Direct digest, request mutation, malformed
envelope, denied-control, and safe-abstention cases remain covered.

The current M22-07 contract/runtime/adversarial/interface/evaluator run passes
36 tests. Existing M22-07 release evidence remains authoritative for the
broader evaluator, benchmark, package, and coverage receipts.
