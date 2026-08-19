# M03-05 result-boundary hardening

This additive hardening keeps the frozen M03-05/M03-06 contracts and their
non-inference ceilings unchanged. It closes an ingress-shape inconsistency in
the M03-05 service verifier: raw JSON was bounded by
`M0305_MAX_CANONICAL_RESULT_BYTES`, but typed model and mapping inputs were
canonicalized without applying the same 8 MiB result ceiling. A caller could
therefore bypass the declared result resource bound by selecting a non-JSON
service entrypoint.

`M0305Service.verify` now canonicalizes every result shape through one bounded
helper before strict contract validation. M03-06 already had this behavior and
is covered alongside M03-05 by the lifecycle suite. The contract validators
continue to perform their existing deterministic replay, relational closure,
digest, provenance, and false-only inference checks; no ABI field or scientific
claim was widened.

Evidence:

- M03-05/M03-06 lifecycle selection: 32 passed with coverage disabled.
- Regression coverage exercises oversized typed and mapping M03-05 results and
  the existing M03-06 equivalents; raw JSON remains bounded by strict parsing.
- The change is limited to the M03-05 service boundary and its lifecycle test.
