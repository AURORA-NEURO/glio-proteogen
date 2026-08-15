# M13-03 mechanistic feature constructor

## Authority and status

This implementation is a provisional, dossier-bound lane for
`GLIO-PROTEOGEN-M13-03`. The authoritative dossier is
`GLIO-PROTEOGEN_240_Module_Dossier.md`, SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`,
lines 4444–4487. The dossier names Data engineering as owner, S2 as the
safety class, and G1 as the gate. The public ABI, operation name, media type,
capacities, and endpoint catalogue remain provisional until owner confirmation;
all implementation metadata is marked `0.1.0-provisional`.

## Responsibility

M13-03 constructs an interpretable mechanistic feature object beneath the
Variant-peptide channel and targets `proteotype`. The reference implementation
uses a curated-rule/mechanistic baseline with a pathway activity feature,
topology class, bounded state interval, complete source lineage, signed
relations, explicit unit bounds, and negative-control gating. It emits no
proteotype result itself (`emits_parent=false`).

Inputs are immutable caller-declared mass-spectrometry, genome/transcriptome,
PTM, configuration, identity/lineage, provenance, consent, quality, support,
and intended-use references. Referenced artifacts are never traversed. The
runtime derives deterministic reference scores from content digests so replay
is exact while authority remains with the owning upstream module.

## Safety boundary

The lane fails closed on any control other than accepted configuration,
resolved identity, accepted provenance, granted consent, accepted quality,
accepted support, and accepted intended use. Unsupported, missing, withheld,
N/A, or OOD evidence produces an abstained result with no feature object and a
`review_required` support decision. Negative-control failures produce a failed
diagnostic and abstention. No unresolved evidence is converted to a negative
finding.

M13-03 does not infer identity or consent, mutate upstream material, perform
generic all-omics fusion, issue treatment recommendations, or infer kinase
activity; kinase-state ownership remains with KINOPHOS. Every result carries
seven uncertainty dimensions, source evidence, provenance for all seven
controls, limitations, and a human-review flag while the ABI is provisional.

## Contract and replay closure

The strict Pydantic contracts enforce one value shape per feature, finite
bounded numeric values, unique feature/relation/transformation/artifact IDs,
known relation endpoints, complete lineage, pathway presence, ordered
intervals, and locked configuration. Request digests bind the exact request;
result digests bind the complete result payload. `M1303Plugin` issues an opaque
validate-once capability and rejects duplicate JSON keys, non-finite numbers,
oversized input, unknown fields, and forged execution tokens.

## Verification evidence

- Contract/runtime/interface/evaluator tests: 34 focused tests pass.
- Scoped branch coverage: 98% (570 statements, 114 branch arcs).
- Evaluator fixture: 7 declared, 7 executed, 7 passed; fixture digest is recorded in `release-evidence/m13_03/evaluation.json`.
- Benchmark: 10 deterministic calls; mean and p95 are recorded in `release-evidence/m13_03/benchmark.json` against provisional 2 s / 3 s budgets.
- Ruff and strict MyPy cover all M13-03 source, evaluator, and adapter files.
- Wheel and sdist hashes, member counts, and isolated import are recorded in `release-evidence/m13_03/package.json`.
