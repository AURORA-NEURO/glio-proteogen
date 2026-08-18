# M23-08 replay-integrity evidence

## Scope

M23-08 is a provisional, caller-declared evidence-gate and release
adjudicator. This regression hardening does not authenticate issuer authority,
traverse raw scientific content, infer variant-peptide biology, or expand the
release claim ceiling.

## Replay contract

The M23-08 engine already performs the required ordered replay closure:

1. Strictly validate the result and check the request digest, deterministic
   result identifier, and result payload digest.
2. Re-adjudicate the bound request using the deterministic gate engine.
3. Compare the complete canonical JSON result and fail closed on any
   difference.

The service, strict plugin, FastAPI verify route, and Typer verify command all
use this same engine path. Direct digest failures remain distinguishable from
semantic replay mismatches, and interface errors remain sanitized.

## Regression gap closed

Prior tests covered direct digest tampering and request replacement, but did
not prove that a caller could not edit a contract-valid signed release record,
finding, evidence reference, or provenance record and recompute the outer
`result_digest`. New adversarial coverage exercises those self-rehashed
mutations through service/plugin seams and verifies API/CLI parity.

The complete M23-08 contract/deep/adversarial/runtime/interface/evaluator suite
passes 45 tests. Existing M23-08 release evidence remains authoritative for
package, benchmark, coverage, and release-verifier receipts.
