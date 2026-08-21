# M13 standalone API transport boundaries

The standalone M13 adapters now enforce their declared byte ceilings at the
HTTP transport boundary. This is a resource-safety guarantee, not a change to
the provisional M13 schemas or scientific claims.

## Covered surfaces

M13-01, M13-02, M13-03, M13-04, M13-05, M13-07, and M13-08 each expose a
FastAPI application with a request ceiling and an independent result ceiling.
M13-06 is exposed through the central API, whose shared middleware already
provides the same boundary.

Normal validation/execution routes use the module's canonical request limit.
Replay/verification routes ending in `/verify` use the module's canonical
result limit. The middleware checks `Content-Length` before handing the
request to FastAPI and also counts streamed chunks, so an oversized body
cannot reach JSON decoding, authorization, or module execution.

M13-02 previously installed only its request limit, making its larger result
ceiling unreachable over HTTP. The other standalone adapters had no transport
middleware and relied on later parser checks. The uniform wiring closes both
gaps while retaining each module's existing limits and sanitized 413 response.

The CLI/library file readers remain separately bounded. M13-07's optional
reader limit preserves its existing direct-call compatibility while resolving
the module ceiling at call time, so runtime configuration and tests cannot
silently bypass the limit.

## Evidence

`tests/interfaces/test_m13_api_transport.py` exercises request and verify
routes for every standalone adapter with oversized `Content-Length` values.
The assertions require a 413 response with the sanitized transport detail,
before any body parser or route validator is entered. The focused M13
integration and adversarial suite is run alongside this matrix for regression
coverage.
