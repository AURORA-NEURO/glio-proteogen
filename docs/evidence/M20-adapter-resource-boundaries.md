# M20 standalone adapter resource boundaries

## Scope

This record covers the four standalone M20 file adapters present in the
current tree: M20-01, M20-02, M20-03, and M20-04. No absent or central-only
M20 modules were synthesized. The change is transport-only: no contract,
result model, operation, media type, or scientific claim changes.

## Boundary contract

Request files are admitted through the shared `read_bounded` helper with the
module's `MAX_CANONICAL_REQUEST_BYTES`; result files use the matching
`MAX_CANONICAL_RESULT_BYTES`. The helper reads one sentinel byte beyond the
ceiling and raises before strict JSON decoding or model construction. CLI
verification maps oversized result files to the existing sanitized failure
path.

This closes a concrete resource gap: the prior adapters used unbounded
`Path.read_bytes()`, allowing arbitrarily large local payloads to be
materialized before the declared limit was checked. Existing API behavior and
scientific semantics remain unchanged.

## Verification

The focused matrix covers sparse request/result files one byte over every M20
ceiling, sanitized CLI result failures for all four adapters, and an AST guard
preventing direct `Path.read_bytes()` from returning to the affected files.

* 13 resource-boundary tests passed;
* 26 existing M20 integration/evaluator tests passed;
* 39 focused tests passed with coverage disabled;
* Ruff check/format, strict MyPy, compileall, and `git diff --check` passed.

The evidence is limited to file-admission safety. It is not evidence of
protein, proteoform, isoform, glioma, or other biological inference.
