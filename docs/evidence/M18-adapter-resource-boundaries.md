# M18 standalone adapter resource boundaries

## Scope

This record covers the five standalone M18 file adapters present in the
current tree: M18-01, M18-02, M18-04, M18-05, and M18-07. M18-03, M18-06,
and M18-08 have no standalone file-adapter modules and were not synthesized.
The change is transport-only: no contract, result model, operation, media
type, or scientific claim changes.

## Boundary contract

Request files are admitted through the shared `read_bounded` helper with the
module's `MAX_CANONICAL_REQUEST_BYTES`; result files use the matching
`MAX_CANONICAL_RESULT_BYTES`. The helper reads one sentinel byte beyond the
ceiling and raises before strict JSON decoding or model construction. The
M18-02 and M18-05 path-or-stdin adapters now apply the same request/result
ceilings to both filesystem and stdin inputs. Their HTTP verification paths
also use the explicit result ceiling.

This closes a concrete resource gap: the prior adapters used unbounded
`Path.read_bytes()` (and unbounded stdin reads in M18-02/M18-05), allowing
arbitrarily large local or piped payloads to be materialized before the
declared limit was checked. Existing CLI/API error paths remain sanitized.

## Verification

The focused matrix covers sparse request/result files one byte over every M18
ceiling, stdin overflow for both path-or-stdin adapters, sanitized CLI result
failures, and an AST guard preventing direct `Path.read_bytes()` from
returning to the five affected adapters.

* 15 resource-boundary tests passed;
* 32 existing M18 integration/evaluator tests passed;
* 47 focused tests passed with coverage disabled;
* Ruff check/format, strict MyPy, compileall, and `git diff --check` passed.

The evidence is limited to file/stream admission safety. It is not evidence
of protein, proteoform, isoform, glioma, or other biological inference.
