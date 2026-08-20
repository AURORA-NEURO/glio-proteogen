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
2. checks graph and reproducibility-bundle closure, including exact graph,
   bundle, and deterministic result-ID binding to the request;
3. regenerates the complete result through the deterministic engine; and
4. compares the canonical JSON of every result field.

The locked evaluator and adversarial suite include a self-rehashed provenance
mutation. The independent release verifier locks the ordered scenario IDs so a
receipt cannot report only a digest-tamper case while omitting semantic replay.

FastAPI request and replay bodies now drain under the 4 MiB request / 8 MiB
result ceilings before strict parsing; direct service mappings enforce the same
limits before model validation.

Lineage graph cycle validation traverses every incoming parent edge. A cycle
hidden behind a second parent for the same child cannot be masked by a
single-parent projection and is rejected before graph construction.

Evidence gates on the current-main lane: 31 focused tests, 96.0% scoped
branch-enabled coverage (586 statements, 114 branches; fail-under 95), fresh
10-round benchmark mean 2,518,761 ns and p95 3,473,500 ns, two byte-identical
SOURCE_DATE_EPOCH builds, and isolated imports of the package and M26-02
namespace.
