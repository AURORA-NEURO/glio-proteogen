# M20-05 through M20-08 CLI resource-boundary hardening

## Finding

The four provisional biomarker-panel CLI adapters declared request and result
byte ceilings in their contracts, but their file adapters did not enforce the
ceilings uniformly. Request files were read in full before the bounded JSON
parser, while result files were read directly into Pydantic validation without
any byte limit. This made the CLI transport boundary weaker than the shared
service/API/plugin paths.

## Fix

All four adapters now use the existing `glio_proteogen.adapters.limits.read_bounded`
streaming helper before parsing:

| Module | Request ceiling | Result ceiling |
| --- | ---: | ---: |
| M20-05 | 4 MiB | 8 MiB |
| M20-06 | 4 MiB | 8 MiB |
| M20-07 | 4 MiB | 8 MiB |
| M20-08 | 4 MiB | 8 MiB |

The helper reads at most the configured ceiling plus one byte, so oversized
files are rejected before JSON or Pydantic traversal. Strict JSON parsing now
receives the matching result ceiling as well as the existing request ceiling.
Errors remain sanitized through each module's existing Typer error boundary.

This is transport/resource hardening only. It does not change fields, result
semantics, endpoints, media types, upstream bindings, authority status, or
scientific claims.

## Verification

Each module has adversarial CLI coverage for oversized request and result files
using sparse files that exceed the declared ceiling without requiring a valid
payload. The combined interface suite passes 22 tests, with Ruff, formatting,
and strict MyPy clean for all four CLI adapters.
