# M21-03 replay-integrity evidence

## Scope

M21-03 remains a provisional, caller-declared internal benchmark and ablation
boundary. This hardening does not authenticate M21-02 material, traverse raw
scientific content, run a biological model, or emit a complex-activity claim.

## Defect closed

The previous replay path checked request identity, request digest, and result
payload digest, then revalidated the result envelope. Those checks establish
internal consistency only. A caller able to edit a contract-valid nested
dossier, evidence, finding, or provenance record could recompute the outer
`result_digest` and pass replay.

## Replay contract

Replay now performs ordered closure checks and semantic regeneration:

1. Direct request-digest, result-identifier, and result-digest checks retain
   precise existing errors for forged envelopes.
2. The result is strictly re-parsed and the deterministic M21-03 engine
   regenerates the complete result from its bound request.
3. The full canonical JSON model is compared; any difference fails closed as a
   replay error.

The same semantic check is used through the service, strict plugin, FastAPI
`/v1/modules/M21-03/verify` route, and Typer `verify` command. Interfaces
continue to expose sanitized errors.

## Adversarial coverage

The focused suite includes contract-valid self-rehashed mutations of a dossier
metric, dossier evidence, and provenance activity through service/plugin seams,
plus FastAPI and Typer parity. Direct digest, request/identifier tampering,
malformed envelope, denied-control, and strict-parse cases remain covered.

The current M21-03 contract/runtime/adversarial/interface/evaluator run passes
26 tests. Existing M21-03 release evidence remains authoritative for the
broader evaluator, benchmark, package, and coverage receipts.
