# M14-compatible bulk protein-program evidence facade

## Boundary

`/v2/research/modules/m14/microenvironment-protein-programs` is an additive research facade
over the existing `neftel-bulk-protein-programs/1.0.0` service. It does not copy, relabel, or
reinterpret model logic. `demo`, `analyze`, and `verify` use the exact existing request, result,
and replay contracts, so request, profile, computational, result, source-catalog, bootstrap,
permutation, and replay digests are identical to direct service output. The only new contract is
`profile`, which embeds the delegated algorithm profile and adds an M14 responsibility map.

The facade supplies support-gated **bulk protein program concordance** against the exact Neftel
Table S2 meta-module identities. The source programs came from single-cell GBM research, but the
runtime input and output are bulk-protein evidence. It never emits cell fractions, performs
deconvolution, estimates cell abundance, localizes signals spatially, infers immune composition,
assigns a clinical class, recommends treatment, or replaces governed M14 behavior. Multiple
programs may be supported simultaneously; no winner-take-all cell state or subtype is emitted.

## Placeholder responsibility mapping

The only replaceable placeholder is a synthetic or caller-declared numerical **bulk protein
program score used as evidence**. Its replacement is still subject to the delegated engine's
coverage, method-agreement, uncertainty, null-calibration, and abstention rules. No complete M14
module responsibility is superseded.

| Provisional responsibility | What this facade can supply | What remains unsuperseded |
|---|---|---|
| M14-01 hypothesis registry | Replay-bound program evidence may support a hypothesis | Registration, falsification, competing explanations, and adjudication |
| M14-02 context/subtype stratifier | Real support-gated bulk program scores can replace a program-score stand-in | Context mapping, deconvolution, cell abundance, subtype and clinical classification |
| M14-03 mechanistic feature constructor | Program receipt as source evidence | Mechanistic/topology/lineage/kinetics/spatial/regulatory feature construction |
| M14-04 network/state/mechanism inference | Program receipt as source evidence | Mechanism posteriors, network states, causal effects, cell origin, and kinase activity |
| M14-05 longitudinal/evolution model | Nothing temporal | Trajectories, evolution, and change points |
| M14-06 perturbation/sensitivity simulator | Nothing interventional | Perturbations, parameter sweeps, causal simulation, and treatment effects |
| M14-07 plausibility adjudicator | Program receipt available for review | Orthogonal/negative controls, assay physics, direction, conservation, and conflicts |
| M14-08 mechanism evidence dossier | Receipt may be referenced by a future dossier | Dossier assembly, claim promotion, governance, and owner approval |

Every machine-readable `module_responsibility_superseded` flag is therefore `false`. M14-02 is
`program_evidence_substitution_only`; M14-05 and M14-06 are `out_of_scope`; the remaining
responsibilities are `evidence_source_only`.

## Exact operations and limits

- `GET /v2/research/modules/m14/microenvironment-protein-programs/profile`
- `GET /v2/research/modules/m14/microenvironment-protein-programs/demo`
- `POST /v2/research/modules/m14/microenvironment-protein-programs/analyze`
- `POST /v2/research/modules/m14/microenvironment-protein-programs/verify`

The delegated synthetic demo ID is `synthetic-neftel-ac-program-v1`. Analysis requests retain
the delegated 2 MiB bound, results the 1 MiB bound, and replay envelopes the 4 MiB bound. JSON
ingress requires `application/json` and rejects duplicate keys, non-finite numbers, coercion,
unknown fields, invalid UTF-8, and over-limit streams before model execution. Public errors are
sanitized; all responses disable caching. The facade is stateless and persists nothing.

The isolated router is
`glio_proteogen.adapters.m14_microenvironment_protein_programs_facade.router`. After mounting it,
a containing FastAPI application calls
`install_m14_microenvironment_protein_programs_openapi(app)` to register the strict replay union.
Shared API, deployment catalogue, firewall, CLI, and UI wiring are separate coordinated changes;
existing `/v1/research/neftel-protein-programs` and governed `/v1/modules/M14-*` behavior is
unchanged.
