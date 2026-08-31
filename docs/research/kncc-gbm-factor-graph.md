# KNCC GBM independent two-block factor-graph composition

## Purpose and maturity

`glio-ecgi-kncc-gbm-transition/1.0.0` is a research-use-only integration
surface for two exact, numerically independent child engines:

- the PDC000514 protein/Reactome child,
  `kncc-reactome-conditional-transition/1.0.0`; and
- the PDC000515 phosphosite/SPHINKS child,
  `kncc-gbm-longitudinal-kinase-transition/1.0.0`.

The outer service validates one typed request for each child, runs the existing
Reactome service and then the existing SPHINKS service deterministically in
serial under one outer deadline, and returns both exact child results. It does
not fit coefficients, retrain either child, learn an interaction, or combine
their numerical coordinates. This composition is **not a new independent
fitted model** and does not increase the ten-lane independent-model count. It is
an integrated presentation/composition surface with an outer content-addressed
receipt.

Computational independence here means that neither child consumes the other
child's request or result and that the topology has no cross-block numerical
edge. `independent_parallel_blocks=true` records graph/topology independence,
not concurrent scheduling. It is not a claim that the underlying KNCC evidence
is statistically independent. Both children remain source-cohort concordance
views. Their same-source cohort evaluation is not external validation, and
placing them in one response adds no new validation evidence.

## Exact child semantics

The `protein_reactome` block accepts the exact PDC000514-compatible request and
returns the fitted global recurrence coordinate plus ten conditional Reactome
V97 membership coordinates. These are Reactome concordance, not pathway
activation or flux. They are not causal tumor-evolution, prognostic, or
treatment evidence.

The `phosphosite_sphinks` block accepts the exact PDC000515-compatible
phosphosite request and returns the fixed 24-hypothesis SPHINKS
signature-transition family and four equal-kinase subtype aggregates. These are
SPHINKS signature-transition concordance, not kinase activity or causality.
Kinase labels identify source-locked signatures; they do not establish a
biochemical regulator, subtype probability, prognosis, or treatment response.
Every estimable SPHINKS child result retains its child-defined `LIMITED` state.

The outer result preserves child missingness, censoring, support, uncertainty,
quality states, limitations, and ablations without remapping. There is no
cross-modal fusion/feedback: no SPHINKS value changes the Reactome calculation,
no Reactome value changes the SPHINKS calculation, and neither block upgrades
the other's evidence state.

## Locked topology

The topology identifier is
`kncc-gbm-independent-two-block-factor-topology/1.0.0`. Its exact inventory is:

| Node family | Count | Role |
|---|---:|---|
| computation-block containers | 2 | one container for each exact child |
| Reactome global recurrence factor | 1 | child source-cohort fitted coordinate |
| Reactome pathway factors | 10 | child source-cohort fitted coordinates |
| SPHINKS kinase-signature factors | 24 | child source-cohort fitted coordinates |
| SPHINKS subtype-signature factors | 4 | child source-cohort fitted coordinates |
| **all nodes** | **41** | locked presentation inventory |

Each of the 39 factor nodes has one containment edge from its own block
container. All 39 containment edges have relationship `contains`,
`computational_role="annotation_only"`, and `numerical_weight=null`. Cross-block
containment is forbidden. `cross_block_edges` is empty and the numerical
cross-block edge count is exactly zero.

The word “factor graph” therefore describes a locked result inventory and
presentation topology, not a joint probabilistic graph or learned cross-assay
network. The outer layer evaluates no factor-to-factor message, cross-block
weight, fused likelihood, feedback loop, or joint numerical objective.

## Requests, execution, and exact child receipts

An outer request supplies `analysis_id`, one strict `reactome_request`, and one
strict `kinase_request` under relationship
`independent_parallel_source_cohort_concordance_no_cross_modal_fusion`. Each
child must contain two through five ordered time points. Child-specific assay,
normalization, observation, work-budget, and support contracts continue to
apply.

The result embeds `reactome_result` and `kinase_result` without projecting them
onto a common scale. Its provenance contains an exact child receipt for each
block:

- `child_profile_id` and `child_profile_digest` bind the locked child runtime;
- `child_request_digest` binds the normalized modality-specific child request;
- `child_result_digest` binds the complete child result; and
- `independently_computed=true` records the no-fusion numerical relationship,
  not concurrent execution.

The outer result separately binds `profile_digest`, `topology_digest`,
`request_digest`, `result_digest`, and `source_inventory_digest`. It repeats the
literal safety invariants `independent_parallel_blocks=true`,
`cross_modal_fusion_performed=false`, and
`numerical_cross_block_edge_count=0`. A child profile, request, or result digest
that disagrees with its nested result is rejected rather than relabeled.

## Provenance and content locks

The outer profile has:

| Binding | Locked value |
|---|---|
| profile ID | `glio-ecgi-kncc-gbm-transition/1.0.0` |
| model ID | `glio-ecgi-kncc-gbm-factor-graph/1.0.0` |
| profile digest | `sha256:d3c200ab6a793ce117815a186ef80c6c21cb91b74bc022c6c73c0a6176c84303` |
| topology digest | `sha256:d9baef8ce0b125a26f547edd0441e05c772249fcef3ab57b95d0eea0c777f9c7` |
| source-inventory digest | `sha256:4c785befb48c4eef89598c5480c38248d551df3181f6791d1a9ca8064e9f4aa5` |
| composition-semantic digest | `sha256:d31e7d0122b24700e5aaed497dcf3b0796bc29debb12b4435dbf3807bc3e594d` |
| NumPy runtime | `2.5.2` |
| demo request digest | `sha256:bee98bde0309065837ab39d2be3eb54ed192ac6242ff3a3b4e4e9efa042b0938` |
| demo semantic-oracle digest | `sha256:9dedba0fb288f8a05c1442ef5f6dcec468a0dfa64dc0edb0035b5e846c176bf3` |

The `composition_semantic_digest` covers the canonical Python AST of the outer
canonicalization, contracts, topology, engine, service, profile, and demo
modules. The `source_attestation_state` is `verified_exact_child_snapshots`.
The outer package adds no patient-level source artifact; it inherits source
attribution, license, transformation, privacy, and evaluation boundaries from
the two child profiles.

The exact child profile bindings are:

| Binding | PDC000514 Reactome child | PDC000515 SPHINKS child |
|---|---|---|
| child profile digest | `sha256:91f2f1816deddb74f31d536dc5091ef88d6666ff7b19726705ba0ca1dedfaecb` | `sha256:6be719c54fdaf2be0f83cfe649bc9d394454e5eeb187108a0ce0c7feea9f471a` |
| source digest | `sha256:84732b0bb2c89e82285c7b10fd567c3612eb89ae3a36846df0d7b88b6be59584` | `sha256:3e38ddfc165ff238b7ee8a9c83b16eac799a8d023268319547c47d8eb669fed4` |
| fitted-content digest | `sha256:74cb8b63dbdd7d321fb55e1439bb7cf73bfae415edbdd53fab150f06a00dfd7b` | `sha256:416a5f814378ed141fc89d3dd4bf497489c472cef2db1c16e97ec9ede080c822` |
| bootstrap digest | `sha256:53e44131ea0bb159175a889dcfdc07d941f568e59439a807ad5d82fc38707a3f` | `sha256:c5756048bce4074efe9b1914c325b0cbb5f312e7840efe92d8b926edbb5df38c` |
| evaluation digest | `sha256:6bf513badfd1c005e70718d98e1dd83c6b987b32596d1f13fc33909f2ce8ea69` | `sha256:303d6694a289f9cb3d181aedc732c2c5679830e9daa33f4098521b8f1cd0aa9e` |

The Reactome source admission and fitted recipe are documented in
[`kncc-reactome-conditional-transition-source.md`](kncc-reactome-conditional-transition-source.md)
and
[`kncc-reactome-conditional-transition-model.md`](kncc-reactome-conditional-transition-model.md).
The PDC000515/SPHINKS fit and source boundary are documented in
[`longitudinal-gbm-kinase-transition.md`](longitudinal-gbm-kinase-transition.md).

## Exact replay

Replay accepts the original outer request and result, recomputes both children,
and verifies:

- each child's normalized request digest, profile identity and digest, canonical
  result digest, recomputed result digest, and complete semantic projection;
- the outer request, profile, topology, source-inventory, and result digests;
- exact outer provenance and all non-digest result semantics; and
- independent child execution, no cross-modal fusion, and zero numerical
  cross-block edges.

`verified=true` requires every digest and semantic check to pass. Verification
reports separate `reactome_child_verified` and `kinase_child_verified` fields.
A failed check returns no accepted composed interpretation. Replay is exact
deterministic recomputation of the two child receipts and outer binding; it is
not biological or external validation.

## HTTP, CLI, and limits

The stateless HTTP prefix is `/v1/research/gbm-factor-graph`:

- `GET /profile` returns the content-bound outer profile and topology;
- `GET /demo` returns the versioned wholly synthetic composed request;
- `POST /analyze` runs both exact child engines and returns their nested
  receipts; and
- `POST /verify` recomputes and verifies one request/result envelope.

Expanded paths are
`/v1/research/gbm-factor-graph/profile`,
`/v1/research/gbm-factor-graph/demo`,
`/v1/research/gbm-factor-graph/analyze`, and
`/v1/research/gbm-factor-graph/verify`. HTTP bodies must be strict
`application/json`. Responses use `Cache-Control: no-store` and expose the
applicable `X-GLIO-Profile-Digest`, `X-GLIO-Request-Digest`, and
`X-GLIO-Result-Digest` receipt headers.

The matching CLI group is:

```text
glio-proteogen gbm-factor-graph profile
glio-proteogen gbm-factor-graph demo
glio-proteogen gbm-factor-graph analyze request.json
glio-proteogen gbm-factor-graph verify replay-envelope.json
```

The outer request limit is 4 MiB, result limit is 8 MiB, and replay-envelope
limit is 16 MiB. Each child is limited to two through five time points. The HTTP
adapter admits one whole analysis or verification request at a time per API
process and returns `429` with `Retry-After: 1` when capacity is exhausted. Its
single 120-second deadline begins after slot admission and covers bounded body
reading, strict decoding, validation, and the serial Reactome-then-SPHINKS
execution. Caller disconnects cancel bounded work. Direct calls through the
exported service facade and the CLI retain the byte and child-contract limits
but do not use the HTTP admission semaphore. The lower-level engine function
assumes service-admitted typed input and is not a transport or resource-
admission boundary. No interface persists requests or results.

## Synthetic demo and claim ceiling

The demo identifier is
`kncc-gbm-factor-graph-synthetic-model-derived-v1`. It combines the two exact
versioned child demos without remapping. All demo observations are synthetic
model-derived observations; they are not KNCC patient measurements, validation
samples, or clinical examples. The demo request and semantic-oracle digests are
profile-bound so a changed child demo, topology, or independence invariant fails
closed.

The outer safety class is `research_use_only` and its literal claim ceiling is
`independent_source_cohort_concordance_coordinates_only`. “Independent” in that
field refers to the two numerical child computations, not an independent
cohort. The scientifically safe reading is:

- source-cohort concordance only;
- Reactome concordance, not activation/flux;
- SPHINKS signature-transition concordance, not kinase activity/causality;
- no cross-modal fusion/feedback;
- same-source cohort, not external validation; and
- research-only, non-diagnostic, non-prognostic, and non-prescriptive.

The composition does not authorize a joint multi-omics state, tumor-evolution
claim, causal mechanism, recurrence prediction, prognosis, treatment response,
or clinical decision.
