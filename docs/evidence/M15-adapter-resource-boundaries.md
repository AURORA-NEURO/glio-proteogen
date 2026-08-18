# M15 adapter resource boundaries

## Scope

This record covers the five standalone M15 file adapters present in the
current tree: M15-01, M15-03, M15-04, M15-06, and M15-07. M15-02, M15-05,
and M15-08 have no standalone file-adapter modules, so no interfaces were
invented for them. The change is transport-only and does not modify any
provisional contract, result model, operation, media type, or claim ceiling.

## Boundary contract

Every request file is read through `glio_proteogen.adapters.limits.read_bounded`
with its module's `MAX_CANONICAL_REQUEST_BYTES`; every result file uses the
matching `MAX_CANONICAL_RESULT_BYTES`. The shared helper reads one sentinel
byte beyond the ceiling and fails before strict JSON decoding or model
construction. CLI verification converts oversized input to the existing
sanitized failure envelope rather than exposing a traceback.

The previous adapters called `Path.read_bytes()`, so an arbitrarily large
local file could be materialized before the declared limit was enforced. This
fix closes that resource boundary without inspecting or changing scientific
content.

## Verification

The focused matrix covers sparse files one byte over each request and result
ceiling, a CLI result-overflow failure, and an AST guard against reintroducing
direct `Path.read_bytes()` calls. The 12 focused tests pass with coverage
disabled; Ruff check/format, strict MyPy, compileall, and `git diff --check`
are clean. The evidence is limited to file-admission safety and is not
evidence of protein, proteoform, isoform, glioma, or clinical inference.
