# GBM microenvironment evidence graph

`gbm-microenvironment-graph/1.0.0` is a research-only composition lane. It
executes the exact Neftel Table S2 bulk-protein program runtime first, then
projects three source families' complete location and competitive-rank
estimates into the `glio-ecgi/1.0.0` signed evidence graph. When the optional
published GBM proteomic-axis request is present, all seven source signatures
are retained as independent molecular-program observations.

The bridge can also carry an optional, independent secondary observation lane
from `gbm-proteomic-axes/1.0.0`. All seven published signatures (KRAS, MYC,
hypoxia, mesenchymal, neural, proneural, and EGFR) are projected onto matching
graph nodes as `external`-modality observations with their own result digest,
interval-derived standard error, and source quality. A profile-bound
standard-error floor of `0.35` is applied because the published axis bootstrap
captures caller measurement perturbation, not cross-engine scale or calibration
uncertainty. They are never averaged into, substituted for, or allowed to
override the Neftel program evidence. Keeping the modality separate means the
ECGI receipt can ablate the independent axis source on its own, quantifying how
much a context state changes when that source is omitted. Replay requires the
axis request and axis receipt to agree on presence, digest, and semantic
content.

The projection is deliberately narrower than a deconvolution model:

- `mesenchymal_like` maps to the `mesenchymal` graph node;
- `oligodendrocyte_progenitor_like` maps to `opc_like`; and
- `neural_progenitor_like` (the paired NPC1/NPC2 source families) maps to the
  existing `neural` graph node. This is a bulk protein lineage signal, not a
  cellular fraction or categorical subtype call; and
- each complete source location estimate is retained as the historical base
  observation while each complete rank estimate is retained as a distinct
  `.rank` observation on the same node. Location and rank use profile-bound
  standard-error floors (`0.05` and `0.10`) and method-specific quality weights
  (`1.0/0.5` and `0.85/0.40` for supported/limited evidence); and
- the seven published axes map to `kras_targets`, `myc_targets`, `hypoxia`,
  `mesenchymal`, `neural`, `proneural`, and `egfr_targets` in the exact
  profile-declared order. The EGFR axis is connected to hypoxia and
  mesenchymal context, while neural and proneural axes are signed against
  mesenchymal context through lower-weight, profile-bound association
  hypotheses. These edges are not subtype-causality or clinical claims; and
- the independent axis lane uses the `external` modality for observed,
  missing, and unsupported declarations, so source-level ablation remains
  distinct from direct Neftel proteomics; and
- a source family that is not present becomes an explicit `missing` observation,
  while a present family whose own support gate abstains becomes `unsupported`;
  both carry zero quality and neither is treated as negative evidence. The same
  distinction is retained for each optional published axis signature.

The graph relations are a small, versioned GBM microenvironment abstraction:
hypoxia positively connects to angiogenesis and mesenchymal state, mesenchymal
state positively connects to myeloid state, myeloid state is signed against the
T-cell node, OPC-like state is signed against mesenchymal state, and
angiogenesis positively connects to endothelium. Four lower-weight molecular
context edges (EGFR→hypoxia, EGFR→mesenchymal, neural→mesenchymal−, and
proneural→mesenchymal−) allow the published axes to inform downstream context
states without letting a molecular subtype score override direct evidence.
ECGI's robust IRLS solver, one-sided censoring, graph consistency, bootstrap
intervals, and ablations are used without a second proxy score or caller-
declared state. Direct Neftel neural-progenitor evidence and the independent
Verhaak neural axis share the neural node but remain separate observations and
provenance, so either source can be ablated without silently changing the
other.

The source, optional axis, and graph receipts are nested in the bridge result
and replayed independently. The profile binds all child profile digests and
both projection policies. The synthetic demo adds disjoint MES and OPC markers
to the AC-like Neftel fixture and includes the versioned synthetic GBM axis
fixture so the graph surface demonstrates all seven source signatures alongside
cross-modal secondary evidence; those values are synthetic and contain no
patient data.

HTTP operations are mounted under
`/v1/research/gbm-microenvironment-graph` and have matching
`glio-proteogen research-state`-style CLI commands named
`gbm-microenvironment-graph profile|demo|analyze|verify`. Requests and results
are stateless, content-addressed, non-prescriptive, and research-use-only.
Neither program coordinate is a cell fraction, diagnosis, prognosis, causal
claim, or treatment recommendation.
