# M17 adapter resource boundaries

## Scope

This record covers the five standalone M17 file adapters present in the
current tree: M17-02, M17-03, M17-05, M17-06, and M17-07. M17-01, M17-04,
and M17-08 expose interface paths but have no standalone file-adapter
modules; no inferred adapters were added. The change is transport-only and
does not alter contracts, result models, operations, media types, or claims.

## Boundary contract

Every request file is read through the shared `read_bounded` helper with its
module's `MAX_CANONICAL_REQUEST_BYTES`; every result file uses the matching
`MAX_CANONICAL_RESULT_BYTES`. The helper reads one sentinel byte beyond the
ceiling and fails before strict JSON decoding or model construction. CLI
verification maps oversized input to an existing sanitized failure path.

The prior adapters materialized local files with `Path.read_bytes()` before
checking the declared limit. The bounded path closes that resource boundary
without inspecting or changing scientific content.

## Verification

The matrix covers sparse files one byte over every request and result ceiling,
M17-05/M17-07 CLI result-overflow handling, and an AST guard against direct
`Path.read_bytes()` calls. Selected M17 interface suites are included:

* 13 resource-boundary tests;
* 16 existing M17-01/02/04/06/08 interface tests;
* 29 total focused tests passed with coverage disabled;
* Ruff check/format, strict MyPy, compileall, and `git diff --check` clean.

This is transport-safety evidence only, not evidence of protein, proteoform,
isoform, glioma, or clinical inference.
