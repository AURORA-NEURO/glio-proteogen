# M23-05 replay-integrity depth

## Finding

The subgroup evaluator previously checked request identity and the result's
self-reported payload digest, then returned the parsed result. A caller could
change a valid subgroup performance value, recompute `result_digest`, and have
the altered report accepted by replay.

## Correction

`M2305EquityEngine.replay` now canonical-validates the result, retains the
request/identifier/payload binding checks, regenerates the complete evaluation
from the exact canonical request, and compares the full canonical result
projection. This preserves the existing `M2305ReplayError` boundary and does
not alter the contract models, media identifiers, result fields, or provisional
ABI.

The request boundary also retains the exact M23-04 upstream artifact identity
in `source_artifacts`: an upstream entry with the same artifact ID but altered
version, digest, or media type is rejected before evaluation.

## Evidence

- The adversarial suite mutates one performance value and recomputes the result
  digest; semantic replay rejects the forged report.
- The evaluator includes the same self-rehash attack as an executable scenario.
- Existing deterministic, digest-tamper, abstention, authorization, and
  seven-control provenance scenarios remain green.

This is replay-integrity hardening for caller-declared subgroup metadata. It
does not authenticate source truth, infer biology, emit a variant-peptide
conclusion, or promote subgroup metrics to clinical evidence.
