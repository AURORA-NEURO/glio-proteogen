# M18 standalone API transport boundaries

The standalone M18 adapters now enforce their declared byte ceilings at the
HTTP transport boundary. This is a resource-safety correction and does not
change the provisional M18 schemas, replay semantics, or scientific claims.

## Covered surfaces

M18-01, M18-02, M18-04, M18-05, and M18-07 each expose a FastAPI application
with a canonical request ceiling and an independent result ceiling. Normal
execution routes use the request limit; `/verify` routes use the result limit.
For M18-02 and M18-05, the middleware is installed inside `create_app()` so
custom service-backed application instances receive the same boundary as the
module-level app.

The shared middleware checks `Content-Length` before handing the request to
FastAPI and counts streamed chunks as they arrive. An oversized body therefore
receives the sanitized 413 response before JSON decoding, authorization,
contract validation, or module execution. CLI/library readers remain
independently bounded by the same contract constants.

Before this correction, all five standalone M18 applications called
`Request.body()` directly without transport admission. That allowed an
oversized body to reach the parser and made the larger result ceiling
unreachable over HTTP, even though each route checked it after materialization.

## Evidence

`tests/interfaces/test_m18_api_transport.py` covers both request and verify
routes for every standalone M18 adapter with oversized `Content-Length` values.
The assertions require a 413 response with the sanitized transport detail.
The matrix runs with existing resource-limit and integration tests to retain
parser, CLI, replay, and authorization coverage.
