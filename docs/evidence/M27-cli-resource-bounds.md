# M27 CLI resource-bound evidence

The M27-03, M27-05, M27-06, M27-07, and M27-08 Typer adapters now enforce the
canonical request and result byte ceilings before JSON or Pydantic parsing.
Each path uses the shared bounded reader, which reads at most `max_bytes + 1`
bytes and rejects the overflow without retaining an unbounded file payload.
M27-03, M27-05, and M27-06 additionally pass the result ceiling to strict JSON
parsing; M27-07 and M27-08 use the bounded bytes directly for strict model
validation. Overflow and filesystem failures are converted to sanitized CLI
errors, with no internal exception names or traceback exposed.

| Module | Request ceiling | Result ceiling |
| --- | ---: | ---: |
| M27-03 | 4 MiB | 8 MiB |
| M27-05 | 4 MiB | 8 MiB |
| M27-06 | 4 MiB | 8 MiB |
| M27-07 | 4 MiB | 8 MiB |
| M27-08 | 8 MiB | 16 MiB |

`tests/integration/test_m27_cli_bounds.py` exercises both validate/request and
verify/result commands for every module with sparse files one byte above the
declared limit. The test asserts nonzero rejection and confirms that neither
`Traceback` nor `RequestBodyTooLargeError` is exposed.

This is an interface/resource hardening change only. Contract versions,
schemas, media types, operation semantics, provisional metadata, and result
digests are unchanged.

M27-08's FastAPI boundary now applies the same ceilings before parsing request
or result bodies. Its service boundary also bounds JSON strings, bytes, and
mapping inputs after canonical re-encoding, so callers cannot bypass the
declared request limit by supplying an in-memory mapping instead of raw JSON.
Duplicate keys and non-finite JSON numbers are rejected by the shared strict
parser at both transport and service boundaries.
