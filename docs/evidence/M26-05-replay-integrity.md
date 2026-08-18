# M26-05 replay-integrity hardening

## Finding

The previous verifier checked that the embedded request digest and result
payload digest were internally consistent. That is necessary, but not
sufficient: an actor who mutates a telemetry stream, finding, alert, or other
result field can recompute `result_digest` and produce a self-consistent
forgery. The verifier did not recompute the deterministic output from the
embedded request.

## Fix

`verify_telemetry_result` now evaluates the embedded request through the same
M26-05 engine and compares the complete canonical result projection. Existing
request/result digest and status-closure checks remain in place as cheap early
rejections. The service, strict plugin, FastAPI verify route, and Typer verify
command all use this verifier, so they inherit the same replay closure.

No contract field, media type, endpoint, provisional authority, telemetry
semantics, or scientific claim changed. This is an ABI-preserving authenticity
and replay-integrity correction.

## Adversarial coverage

The adversarial suite now forges a nested telemetry sample and finding while
recomputing the payload digest. Direct engine verification, the typed service,
and plugin replay reject the forged result. The FastAPI verify route returns a
sanitized 422 response and the Typer verify command exits nonzero without
leaking internals.

Focused M26-05 gates: 31 tests passed; Ruff, formatting, and strict MyPy for
the touched engine passed.
