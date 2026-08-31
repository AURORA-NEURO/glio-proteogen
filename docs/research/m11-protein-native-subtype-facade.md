# M11-compatible published protein-axis evidence facade

## Boundary

`/v2/research/modules/m11/protein-native-subtype` is an additive research facade over the
existing MIT-licensed `gbm-proteomic-axes/1.0.0` service. It does not copy or reinterpret
model logic. `demo`, `analyze`, and `verify` use the exact existing request, result, and replay
contracts, so request, profile, computational, result, source, and replay digests are identical
to direct service output. The only new contract is `profile`, which describes the facade and
embeds the complete delegated model profile.

The facade supplies published continuous **bulk-protein axis evidence** from seven exact
Diamandis-lab XGBoost ensembles. It is not a posterior subtype classifier, longitudinal or
evolutionary model, clinical class, mechanism or causal estimator, treatment recommender, or
governed M11 replacement. The word `subtype` in the route identifies the intended M11 research
integration boundary; it does not promote axis scores into a subtype label.

## Placeholder responsibility mapping

The only placeholder this lane can replace is a synthetic or caller-declared numerical
**bulk protein-axis score used as evidence**. Even there, the underlying result remains a
continuous signature-score receipt with explicit coverage and abstention semantics; it does
not supersede the whole M11-02 context/subtype responsibility.

| Provisional responsibility | What this facade can supply | What remains unsuperseded |
|---|---|---|
| M11-01 hypothesis registry | Replay-bound axis evidence may support a hypothesis | Registration, falsification, competing explanations, and adjudication |
| M11-02 context/subtype stratifier | Real fitted bulk protein-axis scores can replace an axis-score stand-in | Context mapping and posterior subtype classification |
| M11-03 mechanistic feature constructor | Axis receipt as source evidence | Mechanistic/topology/lineage/kinetics/spatial/regulatory feature construction |
| M11-04 network/state/mechanism inference | Axis receipt as source evidence | Posterior mechanisms, network states, causal effects, and kinase activity |
| M11-05 longitudinal/evolution model | Nothing temporal | Trajectories, evolution, and change points |
| M11-06 perturbation/sensitivity simulator | Nothing interventional | Perturbations, parameter sweeps, causal simulation, and treatment effects |
| M11-07 plausibility adjudicator | Axis receipt available for review | Orthogonal and negative controls, direction, conservation, and conflict adjudication |
| M11-08 mechanism evidence dossier | Receipt may be referenced by a future dossier | Dossier assembly, claim promotion, governance, and owner approval |

Every module-level `module_responsibility_superseded` flag in the machine-readable profile is
therefore `false`. M11-02 alone is marked `axis_evidence_substitution_only`; M11-05 and M11-06
are `out_of_scope`; the other responsibilities are `evidence_source_only`.

## Exact operations and limits

- `GET /v2/research/modules/m11/protein-native-subtype/profile`
- `GET /v2/research/modules/m11/protein-native-subtype/demo`
- `POST /v2/research/modules/m11/protein-native-subtype/analyze`
- `POST /v2/research/modules/m11/protein-native-subtype/verify`

Analysis requests retain the delegated 2 MiB bound, results the 1 MiB bound, and replay
envelopes the 4 MiB bound. JSON ingress requires `application/json`, rejects duplicate keys,
non-finite numbers, coercion, unknown fields, invalid UTF-8, and over-limit streams before
model execution. Public errors are sanitized and all responses disable caching. The facade is
stateless and does not persist requests or results.

The router is mounted through the central API, route-derived deployment catalogue, and
research firewall allowlist. It is deliberately not exposed as a separate CLI or UI model.
Existing `/v1/research/gbm-proteomic-axes` and governed `/v1/modules/M11-*` behavior is
unchanged.
