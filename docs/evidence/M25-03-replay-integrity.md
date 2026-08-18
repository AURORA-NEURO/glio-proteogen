# M25-03 replay-integrity evidence

## Scope

M25-03 remains the provisional, metadata-only internal benchmark and ablation
boundary. This hardening does not expand the ABI, authenticate the caller's
M25-02 artifact, traverse scientific content, or make a proteotype or biology
claim.

## Defect closed

The previous replay path checked the request digest, result identifier, and
result payload digest. Those checks establish internal consistency, but they
do not establish provenance: a party able to edit a nested dossier, finding,
evidence, or provenance record could recompute `result_digest` and produce a
self-consistent forged result.

## Replay contract

Replay now executes in two ordered phases:

1. Parse the immutable result and retain the existing request-digest,
   result-identifier, and result-digest failures for malformed or directly
   forged envelopes.
2. Regenerate the result from the validated, request-bound input using the
   deterministic M25-03 engine and compare the complete canonical JSON model.

Any nested mutation therefore fails even when the attacker recomputes the
outer payload digest. The same semantic check is used by the service, strict
plugin, FastAPI `/v1/modules/M25-03/verify` route, and Typer `verify` command;
interfaces expose only sanitized replay errors.

## Adversarial coverage

The focused M25-03 suite covers self-rehashed mutation of a dossier metric,
provenance activity, and dossier evidence through the service/plugin seam,
plus API and CLI parity. Direct digest, request-digest, identifier, duplicate
finding, malformed envelope, and denied-control cases remain covered.

The current focused runtime/adversarial/interface run passes 48 tests. The
existing M25-03 evidence matrix remains the source of truth for the broader
contract, evaluator, benchmark, and package gates.
