# M26-02 replay-depth evidence

M26-02 remains a provisional, traceability-only lineage service. This change
does not widen its ABI, infer protein subtype biology, or authenticate the
caller-declared M26-01 registry artifact.

The previous verifier checked the request digest and, for built results, the
lineage graph and graph-binding digests. It did not regenerate the result from
the embedded request, so a caller could alter an unconstrained provenance field
and reseal `result_digest` while retaining a structurally valid envelope.

The replay path now:

1. validates the request and result payload digests;
2. checks graph and reproducibility-bundle closure;
3. regenerates the complete result through the deterministic engine; and
4. compares the canonical JSON of every result field.

The locked evaluator and adversarial suite include a self-rehashed provenance
mutation. The independent release verifier locks the ordered scenario IDs so a
receipt cannot report only a digest-tamper case while omitting semantic replay.

Evidence gates on the current-main lane: 31 focused tests, 96.0% scoped
branch-enabled coverage (586 statements, 114 branches; fail-under 95), fresh
10-round benchmark mean 2,518,761 ns and p95 3,473,500 ns, two byte-identical
SOURCE_DATE_EPOCH builds, and isolated imports of the package and M26-02
namespace.
