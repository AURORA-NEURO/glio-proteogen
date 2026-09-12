# GBM microenvironment evidence graph

`gbm-microenvironment-graph/1.0.0` is a research-only composition lane. It
executes the exact Neftel Table S2 bulk-protein program runtime first, then
projects the two program families' complete location and competitive-rank
estimates into the `glio-ecgi/1.0.0` signed evidence graph.

The bridge can also carry an optional, independent secondary observation lane
from `gbm-proteomic-axes/1.0.0`. The published Winter hypoxia and Verhaak
mesenchymal signatures are projected onto the matching graph nodes with their
own result digest, interval-derived standard error, and source quality. A
profile-bound standard-error floor of `0.35` is applied because the published
axis bootstrap captures caller measurement perturbation, not cross-engine scale
or calibration uncertainty. They are never averaged into, substituted for, or
allowed to override the Neftel program evidence. Replay requires the axis
request and axis receipt to agree on presence, digest, and semantic content.

The projection is deliberately narrower than a deconvolution model:

- `mesenchymal_like` maps to the `mesenchymal` graph node;
- `oligodendrocyte_progenitor_like` maps to `opc_like`; and
- each complete source location estimate is retained as the historical base
  observation while each complete rank estimate is retained as a distinct
  `.rank` observation on the same node. Location and rank use profile-bound
  standard-error floors (`0.05` and `0.10`) and method-specific quality weights
  (`1.0/0.5` and `0.85/0.40` for supported/limited evidence); and
- all other families, including absent source families, become explicit
  `missing` observations with zero quality rather than negative evidence.

The graph relations are a small, versioned GBM microenvironment abstraction:
hypoxia positively connects to angiogenesis and mesenchymal state, mesenchymal
state positively connects to myeloid state, myeloid state is signed against the
T-cell node, OPC-like state is signed against mesenchymal state, and
angiogenesis positively connects to endothelium. ECGI's robust IRLS solver,
one-sided censoring, graph consistency, bootstrap intervals, and ablations are
used without a second proxy score or caller-declared state.

The source, optional axis, and graph receipts are nested in the bridge result
and replayed independently. The profile binds all child profile digests and
both projection policies. The synthetic demo adds disjoint MES and OPC markers
to the AC-like Neftel fixture and includes the versioned synthetic GBM axis
fixture so the graph surface demonstrates both supported directions and
cross-modal secondary evidence; those values are synthetic and contain no
patient data.

HTTP operations are mounted under
`/v1/research/gbm-microenvironment-graph` and have matching
`glio-proteogen research-state`-style CLI commands named
`gbm-microenvironment-graph profile|demo|analyze|verify`. Requests and results
are stateless, content-addressed, non-prescriptive, and research-use-only.
Neither program coordinate is a cell fraction, diagnosis, prognosis, causal
claim, or treatment recommendation.
