# C06–C08 CLI resource boundaries

## Scope

This hardening closes the remaining unbounded local-file and stdin reads in the
C06 protein-abundance, C07 copy-number, and C08 transcript/protein-discordance
module CLIs. It is an adapter-only change: no contract fields, scientific
claims, provisional ABI, or result semantics are changed.

Each CLI now uses the shared `read_bounded` transport primitive with its
module-specific `MAX_CANONICAL_REQUEST_BYTES` ceiling. The M07-07 stdin path
reads at most `limit + 1` bytes before strict JSON parsing, so an oversized
stream is rejected without materializing an attacker-controlled payload.

## Evidence

- 13 module CLIs are covered: M06-02, M06-05, M06-07, M07-01, M07-02,
  M07-05, M07-06, M07-07, M08-02, M08-05, M08-06, M08-07, and M08-08.
- 13 parametrized oversized sparse-file cases fail with
  `RequestBodyTooLargeError` before model/JSON validation.
- An AST regression rejects `read_bytes` and zero-argument `read()` calls in
  the scoped CLI sources; bounded stdin reads remain explicitly argumented.
- Ruff check/format and strict MyPy pass on all 13 CLIs and the regression
  test; the focused resource test suite passes 14/14.

This evidence establishes transport safety only. It is not a scientific
validation claim and does not promote any provisional module ABI.
