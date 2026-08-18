# M14 adapter resource boundaries

## Scope

This record covers the six standalone M14 file adapters present in the
current tree: M14-01, M14-02, M14-04, M14-06, M14-07, and M14-08. M14-03 and
M14-05 expose interface paths but do not have standalone file-adapter
modules, so no synthetic adapters were added. The change is transport-only;
it does not alter a provisional contract, result model, operation, media type,
or scientific claim.

## Boundary contract

Each request file is read through the shared `read_bounded` helper with its
module's `MAX_CANONICAL_REQUEST_BYTES`. Each result file uses the matching
`MAX_CANONICAL_RESULT_BYTES`. The helper reads one sentinel byte beyond the
ceiling and raises before strict JSON decoding or Pydantic model construction
when the payload is oversized. CLI verification maps that failure to the
adapter's existing sanitized error path.

This closes a concrete resource gap: the prior adapters called
`Path.read_bytes()`, allowing an arbitrarily large local file to be fully
materialized before the declared contract limit was checked. No API body
middleware behavior changed, and no raw scientific input is inspected by this
hardening.

## Verification

The focused matrix covers sparse files exactly one byte over every M14 request
and result ceiling, a CLI result-overflow failure, and an AST guard that
prevents direct `Path.read_bytes()` from returning to any affected adapter.
The existing M14 interface suites are included in the gate:

* 14 resource-boundary tests;
* 24 existing M14-03/05/02/07 interface tests;
* 38 total focused tests passed with coverage disabled;
* Ruff check and format clean;
* strict MyPy clean for all six adapters and the new test module;
* compileall and `git diff --check` clean.

The evidence is limited to file-admission safety. It is not evidence of
protein, proteoform, isoform, glioma, or other biological inference.
