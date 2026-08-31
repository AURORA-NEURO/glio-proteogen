# Evidence-Conserving Graph Inference (`glio-ecgi/1.0.0`)

## Scope and baseline

This research lane was started from `AURORA-NEURO/glio-proteogen` `main` at
commit `b0339c55e1efad82997caefe8ffe030389f0e23e` and is developed on
`feature/research-evidence-graph`. Existing governed v1 contracts and their
schema digests are not modified by this profile.

`glio-ecgi/1.0.0` evaluates structured, standardized evidence. It does not
ingest raw mzML or FASTA data, persist samples, classify a patient, recommend a
treatment, or automate an action. “Evidence-conserving” describes the software
rules below; it is not a claim of biological novelty or clinical validation.

## Input state semantics

The request is a bounded heterogeneous graph of proteins, proteoforms,
phosphosites, complexes, pathways, and kinases. Relations are typed, directed,
signed, and reliability weighted. Each evidence item binds to one node and
declares exactly one state:

- `observed`: a two-sided standardized effect and standard error;
- `left_censored`: an upper-bound observation retained with one-sided loss;
- `missing`: no numerical contribution;
- `unsupported`: explicitly outside available support, also with no numerical
  contribution.

Missing and unsupported evidence never becomes a zero or negative
observation. Contract validation rejects duplicate identifiers, parallel
source-target-kind relations, unresolved
references, incompatible relation endpoints, non-finite/out-of-range values,
and graph sizes above the declared limits.

## Topology provenance

`topology_provenance` is an optional, strict request declaration. When present,
its topology digest must exactly match the canonical node/edge graph, each
public source must have a unique ID, and every source scope must reference a
node in that graph. Each source records an HTTPS artifact URL, resource release,
record ID and title, media format, byte length, SHA-256, license, retrieval date,
and the graph nodes for which it supplies biological context. The complete
declaration is request-digest bound, copied into result provenance, and checked
again by deterministic replay. Omission does not imply public support.

The versioned demo uses three expert-curated human pathway records from
[Reactome](https://reactome.org/dev/content-service/), retrieved as SBML Level 3
Version 1 from release 97 on 2026-08-27. Reactome describes its annotation data
as [CC0 public data](https://reactome.org/about/news/97-updated-license-agreement).

| Reactome record | Demo scope | SBML bytes | Locked SHA-256 |
|---|---|---:|---|
| [R-HSA-177929 — Signaling by EGFR](https://reactome.org/content/detail/R-HSA-177929) | `pathway.RTK.signaling` | 715,097 | `8bfd16fd5aa56ac37ff1d3e8e1bc8a14f27d5ca9cf4204bcfc2231e004823260` |
| [R-HSA-1257604 — PIP3 activates AKT signaling](https://reactome.org/content/detail/R-HSA-1257604) | `pathway.PI3K.AKT.mTOR` | 1,085,445 | `8274c7abb68f83738c46b7156f81f2546a51720f57ef5997c1353de92aeb4c1a` |
| [R-HSA-69278 — Cell Cycle, Mitotic](https://reactome.org/content/detail/R-HSA-69278) | `pathway.cell.cycle` | 3,546,893 | `5c14a87dc086a50327c09191e001d7d1cb86231eaf34646cc8f4c3555df62ad4` |

These records provide biological context for the three pathway labels only.
The 64-node abstraction, edge selection, signs, weights, essential-subunit
flags, and all observations are deliberately repository-native synthetic demo
choices. They are not represented as exact Reactome assertions, an imported
Reactome network, patient data, or biological validation. A source digest lets
a caller detect a changed remote export; it does not claim that the repository
archives or redistributes that artifact.

## Numerical engine

For latent node vector $x$, active observation evidence $y$, and directed signed
relations, each sweep freezes parent states at $x^{(k)}$ and minimizes one
target-conditional robust loss for every node $j$:

$$
\ell_j(z\mid x^{(k)}) =
     \sum_{i:n(i)=j} q_i\,\rho\!\left((z-y_i)/s_i\right)
     + \sum_{e:t(e)=j} w_e\,\rho\!\left(z-\sigma_e x^{(k)}_{s(e)}\right)
     + L_{complex,j}(z\mid x^{(k)}) + L_{feedback,j}(z)
     + \frac{\lambda}{2}z^2.
$$

`rho` is Huber loss. Left-censored observations contribute only when the
estimate violates their declared upper bound. The complex term combines
member coherence with an asymmetric essential-subunit bottleneck: a complex
cannot receive unpenalized support above an essential member. Pathway state is
therefore propagated through the directed signed topology, rather than being
calculated as an independent pathway average.

A left-censored observation by itself is direction-informative only when its
upper bound is strictly below the suppression threshold. Otherwise it cannot
turn the ridge origin into a supported neutral estimate. Such a node abstains
unless observed evidence or q-supported feedback reaches it through the
directed graph; the one-sided bound and its evidence count remain visible.

The solver is deterministic NumPy target-coordinate IRLS fixed-point inference.
All coordinates read the same frozen parent snapshot, so cycles are synchronous,
input-order invariant, and causal evidence travels only from source to target.
The resulting coordinates are damped together. Each trace records the
frozen-parent baseline and accepted candidate conditional loss as a pair for
every sweep; each candidate must not exceed its paired baseline. Termination
requires the maximum undamped fixed-point residual to meet the profile
tolerance. The paired trace and its digest remain part of the replay receipt.
This is a directed conditional estimator, not a claim that downstream evidence
minimizes a symmetric global edge objective over upstream sources.

The first pass excludes every `kinase_substrate` edge. Local kinase enrichment
is therefore computed from phosphosite states that have not already been
coupled to kinase nodes. Only q-supported local kinase estimates are injected
as feedback before the second pass; only substrate edges sourced by those
supported kinase nodes then become active. Edges from sparse or non-significant
kinases remain inert, so an abstained kinase's ridge-zero coordinate cannot pull
measured phosphosites toward a manufactured neutral state. Supported edges can
influence downstream topology without silently replacing measured evidence. A
required solve that does not converge emits no result.
Bootstrap and ablation solves first use the declared relaxed budget, retry from
their last iterate with the full budget, and fail closed if that retry does not
converge.

## Kinase inference

Kinase candidates use only exact `kinase_substrate` relations to measured
phosphosite nodes. Reliability-weighted signed substrate ranks yield a local
enrichment statistic. Deterministic stratified permutations preserve evidence
strata, empirical p-values include the observed statistic, and the complete
kinase family receives Benjamini–Hochberg q-values. Fewer than three mapped
substrates forces abstention. Mapped but non-significant kinases retain their
enrichment statistic, p-value, and q-value for inspection, but abstain from
graph activity rather than manufacturing a neutral estimate.

The locked null oracle runs 500 deterministic all-null kinase screens. Because
every tested hypothesis is null, each run's false-discovery proportion is one
when it makes any discovery and zero otherwise; the mean is the empirical FDR.
The gate requires that mean to remain within `0.02` of the profile's `0.10`
q-value threshold (the locked `glio-ecgi/1.0.0` run is `0.086`). This is a
software calibration oracle for the synthetic null generator, not evidence of
calibration on biological cohorts.

An optional external KINOPHOS profile is a comparison lane. Exact kinase IDs
are matched and reported with interval overlap, direction agreement, activity
difference, and rank correlation. External estimates are not pooled into or
allowed to override the local estimate. Every local ID without a complete
comparison is reported as unmatched; exact external IDs whose local estimate
abstained are additionally reported as an explicit diagnostic subset rather
than silently omitted.

## Uncertainty and explanation

The default 64 deterministic bootstrap replicates perturb active observations
using seeds derived from a canonical computational-request digest. That digest
contains node identities and kinds, signed weighted relations, active numerical
evidence, and replicate settings. It excludes opaque sample IDs, display labels,
evidence and topology provenance metadata, comparison-only external KINOPHOS
values, and numerically inactive `missing`/`unsupported` declarations. Those
fields remain bound by the full request and result receipts but cannot alter RNG
streams or numerical inference. This explicit projection policy is itself bound
into the algorithm-profile digest and embedded in the computational projection as
a versioned RNG-domain tag. For each replicate, the isolated first pass is rerun and the
main analysis's q-supported kinase set is conditionally rescored before the
second pass; selection and null calibration are not silently repeated inside
the interval procedure. Antithetic normal perturbation pairs reduce finite-draw
quantile noise while preserving the configured Gaussian marginal perturbation law.
The default 64 rows are 32 independent vectors and their exact negatives; an odd
replicate count adds one unpaired Normal vector. Nonlinear and censored solver responses are
not assumed to remain pairwise symmetric. The locked interval oracle covers 176
of 200 simulations (`0.88`) inside the required `0.85`–`0.95` band. Quantized
percentile intervals support replay across identical locked environments.

Every edge-family and evidence-modality ablation reruns the full two-pass
estimator, including substrate mapping, rank enrichment, permutations,
Benjamini-Hochberg selection, feedback construction, and the directed second
pass. Permutations use common random numbers from the base computational-request
domain, so an ablation changes the omitted evidence or topology but not its null
draws. Thus an omitted phosphoproteomic or kinase-substrate source cannot leave
behind a kinase call inferred from that omitted source. Activity differences at
or below the profile-bound relaxed-solver tolerance are reported as zero rather
than presented as biological sensitivity below the solver's numerical
resolution.

Intervals determine the state label:

- `activated` only when the full interval is above `+0.25`;
- `suppressed` only when the full interval is below `-0.25`;
- `neutral` only when the full interval is inside `[-0.25, +0.25]`;
- `indeterminate` for every other estimated interval;
- `not_estimable` when the engine abstains.

Every estimated node reports evidence counts, bootstrap stability,
discordance, top signed drivers, and ablation effects. Every abstention reports
its reason.

## Replay and profile binding

The algorithm profile digest binds NumPy `2.5.2`, the numerical constants,
relation weights, convergence tolerance, directed/synchronous update semantics,
first-pass kinase isolation, conditional bootstrap policy, full-pipeline
ablation with common permutation draws, conservative one-sided-censor support,
safety labels, the synthetic demo topology digest, and a
separate digest of the demo's public-source provenance. Profile construction
fails closed if the runtime NumPy version is not exactly `2.5.2`.
Results bind request, profile, observation-source and topology provenance,
solver traces, and semantic content. Replay verification recomputes the request
and reports each digest, trace, and semantic comparison separately.

Limits are 256 nodes, 2,048 edges, 4,096 observations, 128 kinases, 2 MiB per
analysis request, 4 MiB per result, and at most 256 bootstrap replicates. A
replay receipt contains both the accepted request and its result, so the
`/verify` envelope uses a separate 7 MiB replay-receipt bound; this keeps every accepted
analysis verifiable without widening `/analyze`. Kinase enrichment is bounded
at 2,048 deterministic permutation replicates per request.

## Executable performance evidence

The versioned ECGI performance receipt is produced in a fresh Python process,
with coverage subprocess hooks removed and active tracing rejected. It records
the measurement boundary as `fresh-process` and the memory metric as
`fresh-process-lifetime-peak-rss`. Thus the strict `<256 MiB` gate covers the
operating system's lifetime resident-set peak for the ECGI benchmark
executable—including its interpreter, imports, fixtures, warmups, and result
serialization—without charging memory retained by a calling pytest or
application process. Latency remains scoped to the analysis calls: the same
receipt enforces p95 below two seconds for the 64-node demo and below ten
seconds for the maximum structural fixture, excluding process startup and
fixture construction.
