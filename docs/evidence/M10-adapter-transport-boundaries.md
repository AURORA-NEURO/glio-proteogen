# M10 adapter transport boundaries

The M10-04, M10-05, M10-06, and M10-08 FastAPI adapters now enforce their
contract byte ceilings before body materialization or strict JSON parsing.

M10-04/05/06 already had transport middleware, but it supplied only the
request ceiling. Their `/verify` endpoints therefore rejected bodies above
the 4 MiB request limit even though each contract declares an independent
8 MiB canonical result envelope. The middleware now selects the result limit
for the exact `/verify` paths while keeping validation and execution at the
request limit.

M10-08 previously performed `await request.body()` before any transport
admission. It now uses the same request/result middleware, so oversized
`Content-Length` values and streamed bodies receive a sanitized HTTP 413
without reaching the parser or service. The CLI/file readers retain their
existing bounded behavior.

This is resource and transport hardening only. It does not alter the
provisional M10 schemas, scientific claims, replay semantics, or result
contracts. Regression coverage exercises request overflow across all four
adapters and result overflow across all four verify endpoints.
