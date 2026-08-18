# M17 standalone adapter resource boundaries

## Scope

This record covers the five standalone M17 file adapters present in the
current tree: M17-02, M17-03, M17-05, M17-06, and M17-07. M17-01, M17-04,
and M17-08 have no standalone file-adapter modules and were not synthesized.
The change is transport-only: no contract, result model, operation, media
type, or scientific claim changes.

## Boundary contract

Request files are admitted through the shared `read_bounded` helper with the
module's `MAX_CANONICAL_REQUEST_BYTES`; result files use the matching
`MAX_CANONICAL_RESULT_BYTES`. The helper reads one sentinel byte beyond the
ceiling and raises before strict JSON decoding or model construction. The
M17-05 and M17-07 path-or-stdin adapters now apply the same request/result
ceilings to both filesystem and stdin inputs. HTTP verification for M17-03
uses its explicit result ceiling instead of a request-derived multiplier.

This closes a concrete resource gap: the prior adapters used unbounded
`Path.read_bytes()` (and unbounded stdin reads in M17-05/M17-07), allowing
arbitrarily large local or piped payloads to be materialized before the
declared limit was checked. Existing CLI/API error paths remain sanitized.

## Verification

The focused matrix covers sparse request/result files one byte over every M17
ceiling, sanitized CLI result failures for both path adapters, and an AST
guard preventing direct `Path.read_bytes()` from returning to the five
affected adapters.

* 13 resource-boundary tests passed;
* 23 existing M17 integration/evaluator tests passed;
* 36 focused tests passed with coverage disabled;
* Ruff check/format, strict MyPy, compileall, and `git diff --check` passed.

The evidence is limited to file/stream admission safety. It is not evidence
of protein, proteoform, isoform, glioma, or other biological inference.
