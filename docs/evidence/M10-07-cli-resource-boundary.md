# M10-07 CLI resource boundary

## Finding

The M10-07 CLI already declared 4 MiB request and 8 MiB canonical-result
ceilings, but its request, result, and replay-canonical paths used
`Path.read_bytes()` before those ceilings could be enforced. A sparse file
could therefore trigger an unbounded allocation before JSON validation.

## Hardening

The three external-file reads now use the shared `read_bounded` adapter before
strict JSON parsing or replay verification. The existing M10-07 contract
constants and replay semantics are unchanged. Oversized input is rejected
with the CLI's sanitized validation error, and no request/result bytes are
accepted beyond the frozen ceilings.

## Regression coverage

- Sparse files at both exact ceilings plus one byte are rejected.
- A CLI verification run succeeds with `Path.read_bytes` patched to fail,
  covering both result and canonical replay inputs.
- Ruff, format, strict MyPy on the production CLI, compileall, and the
  focused M10-07 contract/runtime/adversarial/interface/evaluator suite pass.

This is pre-parse resource admission only; it does not expand scientific
claims, alter the provisional M10-07 ABI, or change replay identity rules.
