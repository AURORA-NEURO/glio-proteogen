# M13 adapter resource boundaries

## Scope

This evidence record covers the standalone file and stdin adapters for the
M13 family that accept request or result JSON outside the FastAPI body-limit
middleware. It is an infrastructure hardening change only: no M13 contract
fields, operation names, media types, claim ceilings, or scientific behavior
are changed.

The affected adapters are M13-01, M13-02, M13-03, M13-04, M13-05, M13-07,
and M13-08. M13-06 has no standalone file adapter in the current tree.

## Boundary contract

Every file-backed request path reads at most the module's declared
`MAX_CANONICAL_REQUEST_BYTES` plus one sentinel byte. Every file-backed result
path uses the corresponding `MAX_CANONICAL_RESULT_BYTES` value. A payload
larger than the declared ceiling fails before strict JSON decoding or model
construction. M13-02's `-` stdin path uses the same bounded read rather than
calling unbounded `read()`.

The shared `glio_proteogen.adapters.limits.read_bounded` helper performs the
single bounded read and raises `RequestBodyTooLargeError` on the sentinel
byte. CLI adapters convert that error to their existing sanitized failure
envelopes; they do not expose a traceback or a partial parse. Existing API
request middleware remains unchanged.

## Verification

The focused resource-admission matrix exercises both request and result
ceilings for all seven adapters, sparse files at exactly one byte over each
limit, the M13-02 stdin path, and a CLI result-overflow failure. An AST
regression asserts that none of the affected adapters can reintroduce a direct
`Path.read_bytes()` call.

The focused run also includes the existing M13 interface suites:

* 17 resource-boundary tests;
* 33 M13-02/03/06/07/08 interface tests;
* 50 total tests passed with coverage disabled;
* Ruff check and format clean;
* strict MyPy clean for the seven adapters and the new test module;
* `git diff --check` clean.

This evidence is intentionally limited to transport/resource safety. It is
not evidence of new biological inference, protein/proteoform claims, or
clinical validity.
