# M15-08 and M16-03 replay digest closure

M15-08 and M16-03 validated result structure and, when enabled, compared the
result against deterministic reconstruction, but omitted the embedded payload
digest check. Their `replay=False` inspection mode could therefore accept a
structurally valid result carrying a forged result digest.

Both engines now require `result_digest` to equal the canonical digest of the
validated result before honoring the optional deterministic replay switch.
`replay=False` still skips reconstruction for callers that only need integrity
validation; it no longer skips payload-integrity validation. Schemas, result
fields, request identity, and scientific claim ceilings are unchanged.

Adversarial runtime tests cover wrong-digest results with deterministic replay
disabled for both modules, alongside the existing self-rehashed payload tests
that must still fail deterministic replay.
