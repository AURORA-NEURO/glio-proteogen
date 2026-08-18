# M21-02 replay-integrity depth

## Finding

The provisional M21-02 engine previously checked the request digest and the
self-reported result digest, then returned the validated result. A caller could
therefore mutate a synthetic-truth case, recompute `result_digest`, and pass
replay without rerunning the deterministic generator.

## Correction

`M2102Engine.replay` now validates the canonical result, verifies both digest
bindings, regenerates the corpus from the exact canonical request, and compares
the complete canonical result document. Validation failures remain behind the
existing `M2102ReplayError` boundary. The contract models, media identifiers,
request/result digests, and provisional ABI are unchanged.

## Evidence

- 16 focused M21-02 contract/runtime/adversarial tests pass.
- The adversarial suite mutates a generated case and recomputes its result
  digest; semantic replay rejects the forged corpus.
- Existing request-digest and result-digest tamper tests remain green.
- Ruff, format, and strict MyPy pass on the changed engine/test files.

This is replay-integrity hardening for deterministic synthetic metadata. It does
not authenticate the caller-declared M21-01 artifact, inspect raw cohort data,
infer complex activity, or promote synthetic values to biological evidence.
