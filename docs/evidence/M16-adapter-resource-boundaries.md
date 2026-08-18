# M16 standalone adapter resource boundaries

## Scope

This record covers the six standalone M16 file adapters present in the
current tree: M16-01, M16-02, M16-04, M16-05, M16-07, and M16-08. M16-03 and
M16-06 have no standalone file-adapter modules; their central interface paths
already use the shared bounded request loader, so no synthetic adapters were
added. The change is transport-only and does not alter a contract, result
model, operation, media type, or scientific claim.

## Boundary contract

Each request file is read through the shared `read_bounded` helper with its
module's `MAX_CANONICAL_REQUEST_BYTES`. Each result file uses the matching
`MAX_CANONICAL_RESULT_BYTES`. The helper reads one sentinel byte beyond the
ceiling and raises before strict JSON decoding or model construction when a
payload is oversized. CLI verification maps that failure to the adapter's
existing sanitized error path. HTTP result parsing for M16-01, M16-04, and
M16-08 now uses their explicit result ceilings rather than a request-derived
multiplier.

This closes a concrete resource gap: the prior adapters called
`Path.read_bytes()`, allowing an arbitrarily large local file to be fully
materialized before the declared contract limit was checked. No API body
middleware behavior changed, and no raw scientific input is inspected by this
hardening.

## Verification

The focused matrix covers sparse files exactly one byte over every M16 request
and result ceiling, a CLI result-overflow failure, and an AST guard that
prevents direct `Path.read_bytes()` from returning to any affected adapter.

* 14 resource-boundary tests passed;
* 17 existing M16 interface tests passed;
* 31 focused tests passed with coverage disabled;
* Ruff check/format, strict MyPy, compileall, and `git diff --check` passed.

The evidence is limited to file-admission safety. It is not evidence of
protein, proteoform, isoform, glioma, or other biological inference.
