# M14-07: plausibility and negative-control adjudicator

M14-07 is the provisional plausibility and negative-control adjudicator beneath
Microenvironment protein deconvolution. It evaluates caller-declared proteome,
genome, transcriptome, PTM, and mechanism evidence against six release-blocking
controls and emits a plausibility grade or an explicit review-required abstention
for the `protein_subtype` parent.

The ABI is provisional (`0.1.0-provisional`) and inferred only from the authoritative
dossier slice. Operation, media type, schema names, endpoint details, capacities, and
control vocabulary remain implementation metadata pending owner confirmation.

## Scope and safety boundary

The runtime accepts an M14-04 mechanism inference artifact, source artifacts, and
caller-declared controls for orthogonal evidence, known controls, direction,
conservation, assay physics, and competing mechanisms. It does not authenticate the
issuer or infer identity, consent, mutations, relabeling, erasure, kinase activity,
generic all-omics fusion, or direct treatment recommendations. Unsupported evidence
never becomes a negative finding.

Seven upstream controls (approved configuration, identity/lineage, provenance,
consent, quality, support, intended use) are checked before parsing, hashing, or
execution. Rejected, unresolved, withheld, malformed, or hostile controls fail closed.

## Contract and runtime behavior

Every control receives exactly one typed evaluation. Failed, not-evaluable, abstained,
missing, or conflict-bearing controls block release. Passing controls produce a HIGH
provisional grade, supported decision, explicit evidence, seven-dimension uncertainty,
and provenance records. Blocked cases produce no grade, a review-required decision,
an explicit abstention reason, visible findings/conflicts, and `human_review_required`.

The result binds the canonical request digest, derives its result ID from that digest,
and carries a canonical result digest. Replay re-runs the exact request; tampered
digests, changed states, duplicate JSON keys, forged plugin capabilities, and opaque
hostile objects are rejected.

## Interfaces and evaluation

`src/glio_proteogen/adapters/m1407.py` provides strict JSON FastAPI schema, adjudicate,
and verify routes plus Typer schema export, no-overwrite adjudication, and verification.
The plugin uses an issued validate-then-run capability token and shares the same service
and canonical representation.

The locked synthetic evaluator covers passing controls, failed/not-evaluable/abstain
controls, unresolved conflict, missing control, replay/tamper, authorization denial,
and deterministic reconstruction. Evidence metrics are recorded in
`docs/evidence/M14-07.md` and `release-evidence/m14_07/`.

The final scoped gate ran 25 focused tests with 98% branch-enabled coverage
(479 statements, 470 covered; 78 branches, 75 covered; 95% fail-under). The
ten-call benchmark measured 1,791,740 ns mean, 1,703,000 ns median, and
2,283,800 ns p95 against provisional 2e9/3e9 ns budgets. The wheel is 856,863
bytes and the source distribution is 1,472,042 bytes; both were built and the
wheel imported from an isolated target.
