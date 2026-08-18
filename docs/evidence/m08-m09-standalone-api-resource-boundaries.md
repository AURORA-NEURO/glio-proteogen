# M08-07/M09-07 standalone API resource boundaries

## Scope

The M08-07 and M09-07 modules expose standalone FastAPI applications in addition
to the central adapter. Their contract modules define separate canonical request
and result byte ceilings: 4 MiB for requests and 8 MiB for results. Before this
hardening, both standalone applications called `strict_json_loads` with the
kernel default for every route. That made the verification route use the request
ceiling accidentally and left the per-module contract limits implicit at the
standalone boundary.

## Correctness and safety behavior

- `/m08-07/calibrate` and `/m09-07/calibrate` parse with the matching request
  ceiling.
- `/m08-07/verify` and `/m09-07/verify` parse with the matching result ceiling,
  which is the bound for the result-bearing verification document.
- Oversized input is rejected as `json_too_large` before Pydantic validation or
  module execution; submitted keys and values are not echoed.
- Schema discovery routes remain unchanged.
- No contract fields, media types, operation names, or provisional ABI claims
  were changed.

The same lane also closes replay semantics at the service boundary. M08-07 now
binds the result's uncertainty profile and seven-control provenance to the exact
request, matching the existing M09-07 closure. When a caller supplies the
original request to either service's verification method, the service regenerates
the deterministic result and compares the complete canonical projection. A
self-rehashed mutation of a control decision therefore cannot pass verification.
The legacy no-request verifier remains a structural digest check for compatibility;
callers that possess the original request receive full semantic replay.

## Adversarial test matrix

`tests/interface/test_m08_m09_standalone_api_resource_limits.py` covers both
modules and both route classes. It monkeypatches each module's declared limit to
one byte and sends a two-byte JSON body, proving that the route uses its imported
contract constant rather than the generic parser default. The matrix also keeps
schema discovery under test so the boundary change cannot remove the standalone
schema surface.

`tests/modules/test_m08_m09_replay_depth.py` covers self-rehashed control-output
mutations for both modules and M08-07's previously missing provenance and
uncertainty checks. It exercises both structural verification and full
request-bound regeneration.

The tests are intentionally direct-app tests: central API middleware is a
separate boundary and does not prove the behavior of these exported module apps.
