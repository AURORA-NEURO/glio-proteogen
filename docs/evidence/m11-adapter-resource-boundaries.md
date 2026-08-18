# M11 adapter file-resource boundaries

The standalone M11 adapters accept JSON request and result files through their
Typer paths. Before this change, eight adapters used `Path.read_bytes()` or an
equivalent unbounded path read even though each M11 contract already declared
canonical request and result ceilings. That allowed an oversized file to be
fully allocated before strict JSON rejection.

The path readers now use the shared `read_bounded` helper and pass the
contract-specific limit before parsing:

| adapters | request | result |
| --- | ---: | ---: |
| M11-01, M11-02, M11-03, M11-04 | 4 MiB | 8 MiB |
| M11-05, M11-06, M11-07, M11-08 | 4 MiB | 8 MiB |

All eight HTTP applications now install the shared streamed admission
middleware at the declared 8 MiB result ceiling. This is deliberately the
larger transport ceiling: request routes still apply their 4 MiB request
ceiling in the strict JSON parser, while verify routes can accept a result up
to the independent 8 MiB result limit. M11-02 previously installed its
middleware at the smaller request ceiling, so valid-sized result envelopes
were rejected before reaching its result parser. M11-02 also maps the
middleware's `RequestBodyTooLargeError` to a sanitized 413 response instead
of allowing its broad verification `ValueError` handler to downgrade a
stream-overflow to 422.

The adapter changes do not alter schemas, operation names, media types, replay
digests, or the provisional ABI. They close only path and HTTP admission
bypasses and use the declared result ceiling for CLI replay files and strict
result parsing. The middleware rejects an over-limit `Content-Length` before
route dispatch, and rejects chunked bodies as their cumulative bytes cross the
ceiling.

`tests/interfaces/test_m11_adapter_resource_limits.py` covers all eight
request readers, all eight result-reader paths, rejection before parsing, and
a `Path.read_bytes` firewall. Tests use small synthetic overflow files with a
patched limit so the regression does not allocate multi-megabyte fixtures.
`tests/interfaces/test_m11_http_resource_limits.py` covers all eight M11 HTTP
applications across declared over-limit lengths, malformed `Content-Length`,
and chunked transfer without a length header. It uses an 8 MiB streaming
fixture and verifies a sanitized 413 response for every verify route.
