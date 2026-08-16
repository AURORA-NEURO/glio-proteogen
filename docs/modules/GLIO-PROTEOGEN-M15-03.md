# GLIO-PROTEOGEN-M15-03 — mechanistic feature constructor

M15-03 constructs an interpretable mechanistic feature object beneath the Longitudinal
recurrence proteotype. It preserves pathway, topology, state, lineage, kinetics, spatial, and
regulatory feature records tied to the `complex_activity` parent, with source evidence,
units, support, uncertainty, provenance, limitations, and explicit safe failure. The ABI is
provisional (`0.1.0-provisional`) because the dossier freezes behavior and ownership but not a
production endpoint or catalogue.

## Authority and boundary

This implementation is derived from dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact lines 5164–5204.
The owner is Scientific engineering, safety class S2, gate G1. The runtime implements the
deterministic reference projection of the listed curated-rule, enrichment, mechanistic-baseline,
Bayesian/state-space, foundation-assisted, and orthogonal-consensus architectures. It does not
fit a model, dereference external content, claim biological truth, or install a GNN/model store.

M15-03 emits only a mechanistic feature object for parent target `complex_activity`; it never
emits the parent (`emits_parent=false`). KINOPHOS retains kinase-state ownership. Generic
all-omics fusion, direct treatment recommendation, identity inference, consent inference,
upstream relabeling, disagreement erasure, and unsupported-to-negative conversion are outside
the authority boundary.

## Contract and invariant closure

The strict request binds one request ID, seven upstream controls, an opaque M15-02 media type,
locked feature-constructor configuration, units reference, policy, candidate features, and
source artifacts. Feature IDs are unique, feature count is bounded by policy, numeric values are
finite, supported features carry evidence, and every feature is bound to `complex_activity`.
The configured unit domain is explicit (`dimensionless`, `fraction`, `activity`, `abundance`,
`rate`, `score`, `state_probability`, `spatial_index`, or `timepoint`).

The result binds the canonical request digest and derives `result_id` from it. Constructed results
must contain a supported feature object, no abstention reason, and supported status. Abstained
results contain no feature object, an explicit reason, an unsupported/review-required status,
human-review acknowledgement, and no misleading negative feature. Result evidence is restricted
to evidence-role references. Canonical result bytes are checked for replay and tamper.

## Runtime policy

1. Check approved configuration, resolved identity/lineage, provenance, consent, quality,
   support, and intended use before traversing typed feature material.
2. Require a method in the closed provisional reference domain and a locked units/model
   configuration.
3. Require unit, topology, and perturbation gates; reject unresolved, conflicted, or abstained
   candidate features rather than converting them to negative evidence.
4. Construct the feature object with source evidence, locked references, deterministic
   assumptions, seven uncertainty dimensions, seven control provenance records, and explicit
   limitations. Otherwise abstain safely.

The runtime is deterministic and caller-declared: source digests make reconstruction and tamper
checks possible but do not authenticate an assay, reviewer, laboratory, model, or scientific
claim. Human review is required for safe abstention; release promotion, support overrides,
novel/OOD states, unresolved biological conflict, and critical discrepancies remain governed
outside this implementation.

## Interfaces and evidence

FastAPI exposes `GET /v1/m15-03/schema/{name}`, `POST /v1/modules/M15-03/features`, and
`POST /v1/modules/M15-03/verify`. Typer exposes `export-schema`, `construct`, and `verify`.
The strict plugin validates once, binds a token to the exact request digest, and routes all
execution through the service seam. JSON parsing rejects duplicate keys and enforces the request
size cap; CLI output refuses existing paths.

The frozen evaluator contains seven cases: supported construction, limited support, unit-domain
abstention, conflicted-feature abstention, unsupported-method abstention, replay/tamper, and
authorization. The adversarial suite covers duplicate features, upstream media tampering, finite
and unit invariants, invalid result closure, hostile traversal, token boundaries, API/CLI parity,
duplicate JSON, and no-overwrite output.

The release gate requires Ruff, strict MyPy, compileall, focused tests, branch coverage at least
95%, evaluator closure, benchmark budgets, wheel/sdist construction, and isolated wheel import.
The benchmark uses ten public calls after one untimed warmup with 2e9 ns mean and 3e9 ns p95
software budgets. These metrics are regression gates, not biological accuracy or clinical utility.

See the [evidence inventory](../evidence/M15-03.md) and
[traceability matrix](../traceability/GLIO-PROTEOGEN-M15-03.csv).
