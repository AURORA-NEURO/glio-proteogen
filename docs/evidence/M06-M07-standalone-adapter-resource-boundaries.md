# M06/M07 standalone adapter resource boundaries

This evidence record documents a transport-only hardening pass for the
provisional standalone adapters `m06-08`, `m07-03`, `m07-04`, and `m07-08`.
The provisional operation, schema, result claims, and service behavior are
unchanged.

## Boundary

Typer request and result arguments now resolve as paths and are admitted with
the shared bounded reader before strict JSON parsing. The declared 4 MiB JSON
ceiling is therefore enforced before decoding or Pydantic traversal. The
previous unbounded `FileText.read()` paths are gone; the HTTP handlers retain
their existing strict-body behavior.

## Evidence

- six focused sparse-overflow and AST/read-path tests pass;
- Ruff check/format and strict MyPy pass on the four adapters and test file;
- compile and diff checks are clean;
- no contract, schema, endpoint, scientific claim, or governed ABI changed.

The fixture is intentionally a sparse file whose first byte beyond the
ceiling is written, so the test proves rejection without allocating a large
JSON document.
