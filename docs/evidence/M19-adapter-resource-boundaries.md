# M19 standalone adapter resource boundaries

## Scope

This record covers the three standalone M19 file adapters present in the
current tree: M19-01, M19-02, and M19-05. M19-03, M19-04, M19-06, M19-07,
and M19-08 have no standalone file-adapter modules and were not synthesized.
The change is transport-only: no contract, result model, operation, media
type, or scientific claim changes.

## Boundary contract

Request files are admitted through the shared `read_bounded` helper with the
module's `MAX_CANONICAL_REQUEST_BYTES`; result files use the matching
`MAX_CANONICAL_RESULT_BYTES`. The helper reads one sentinel byte beyond the
ceiling and raises before strict JSON decoding or model construction. The
M19-05 path-or-stdin adapter now applies the same request/result ceilings to
both filesystem and stdin inputs, including HTTP verification.

This closes a concrete resource gap: the prior adapters used unbounded
`Path.read_bytes()` (and unbounded stdin reads in M19-05), allowing arbitrarily
large local or piped payloads to be materialized before the declared limit was
checked. Existing CLI/API error paths remain sanitized.

## Verification

The focused matrix covers sparse request/result files one byte over every M19
ceiling, stdin overflow for M19-05, sanitized CLI result failure, and an AST
guard preventing direct `Path.read_bytes()` from returning to the three
affected adapters.

* 9 resource-boundary tests passed;
* 40 existing M19 integration/evaluator tests passed;
* 49 focused tests passed with coverage disabled;
* Ruff check/format, strict MyPy, compileall, and `git diff --check` passed.

The evidence is limited to file/stream admission safety. It is not evidence
of protein, proteoform, isoform, glioma, or other biological inference.
