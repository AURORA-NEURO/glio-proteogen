# M14 standalone API transport boundaries

The standalone M14 adapters now enforce their declared byte ceilings at the
HTTP transport boundary. This is a resource-safety correction and does not
change the provisional M14 schemas, replay semantics, or scientific claims.

## Covered surfaces

M14-01, M14-02, M14-04, M14-06, M14-07, and M14-08 each expose a FastAPI
application with a canonical request ceiling and an independent result
ceiling. Normal execution routes use the request limit; `/verify` routes use
the result limit.

The shared middleware checks `Content-Length` before handing the request to
FastAPI and counts streamed chunks as they arrive. An oversized body therefore
receives the sanitized 413 response before JSON decoding, authorization,
contract validation, or module execution. The CLI/library readers remain
independently bounded by the same contract constants.

Before this correction, all six standalone M14 applications called
`Request.body()` directly without transport admission. That allowed an
oversized body to reach the parser and made the larger result ceiling
unreachable over HTTP, even though the route-level parser checked it after
materialization.

## Evidence

`tests/interfaces/test_m14_api_transport.py` covers both request and verify
routes for every standalone M14 adapter with oversized `Content-Length` values.
The assertions require a 413 response with the sanitized transport detail.
The matrix runs with the existing M14 integration, resource-limit, and
adversarial tests to retain parser, CLI, replay, and authorization coverage.
