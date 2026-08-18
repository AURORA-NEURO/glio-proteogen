# M28-04 canonical resource-boundary hardening

This additive hardening preserves the M28-04 provisional ABI and closes a
resource-consumption gap at every accepted JSON boundary.

## Finding and fix

The gateway already capped byte and string inputs, but two equivalent Mapping
paths did not use those caps:

- Mapping requests were canonicalized and validated without checking the
  resulting request byte length.
- The service replay path accepted a Mapping result without checking the
  canonical result byte length.

The engine now serializes Mapping requests once and enforces the existing
`M2804_MAX_CANONICAL_REQUEST_BYTES` limit before validation. The service applies
the corresponding existing result limit before replay validation. The CLI
pre-read boundary now streams at most `max_bytes + 1` bytes after its metadata
check, closing the stat/read TOCTOU path without an unbounded `Path.read_bytes()`
allocation. No new limit, field, endpoint, media type, or scientific claim was
introduced.

## Verification

- Request cap: 8 MiB (`M2804_MAX_CANONICAL_REQUEST_BYTES`).
- Result cap: 16 MiB (`M2804_MAX_CANONICAL_RESULT_BYTES`).
- Oversized Mapping request/result cases are covered in
  `tests/runtime/test_m2804_runtime.py`.
- Existing oversized CLI request/result pre-read coverage remains in
  `tests/integration/test_m2804_interfaces.py`.
- The complete M28-04 scoped suite passes: 40 tests.
- Ruff, formatted-source checks, and strict MyPy pass for the three touched
  production gateway files.

This remains a transport/resource safety boundary only. M28-08 and all M29
provisional scaffolds are untouched.
