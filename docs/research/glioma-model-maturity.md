# Glioma model maturity and replacement queue

This inventory separates executable scientific inference from contract, lineage,
workflow, and release plumbing. A package being `0.1.0-provisional` does not by
itself mean that it contains a fake model, and a passing schema or replay test
does not make a numerical method scientifically mature.

## Implemented research inference

The mounted additive research namespace currently contains twelve distinct,
independently testable scientific-inference lanes plus one integrated
composition surface. Distinctness in the twelve-lane mounted inventory means
separate algorithms and receipts, not scientifically independent evidence:

- `glio-ecgi/1.0.0`: directed robust evidence-graph inference with censored
  observations, complex bottlenecks, kinase permutations, bootstrap uncertainty,
  and ablations;
- `gbm-proteomic-axes/1.0.0`: an exact runtime port of seven published GBM
  protein-abundance XGBoost ensembles, locked to the author implementation and
  all 28 supplied output oracles; and
- `gbm-rna-tumor-purity/1.0.0`: an exact NumPy runtime port of the published
  5,829→32→16→1 GBMPurity bulk-RNA model, with fail-closed source conversion,
  the published 80% gene-overlap gate, source-parity preprocessing, output
  clipping, exact active-ReLU local decomposition, and replay. The source
  provides one fitted network, so the lane explicitly declines to manufacture
  an uncertainty interval; and
- `neftel-bulk-protein-programs/1.0.0`: a separately identified robust
  bulk-protein evidence model over the exact Neftel Table S2 marker identities
  and ranks; and
- `sphinks-gbm-master-kinase-concordance/1.0.0`: an independently authored,
  source-locked phosphosite concordance model over the 24 subtype-specific
  master-kinase signatures published by Migliozzi et al., with robust one-sided
  estimation, residue-stratified competitive nulls, fixed-family FDR,
  uncertainty, support gates, and ablations.
- `migliozzi-gbm-functional-proteotype/1.0.0`: a source-locked joint robust fit
  of relative GPM, MTC, NEU, and PPR bulk-protein concordance coordinates over
  the exact 600 Table 2d genes, with one-sided censoring, an independent
  source-rank-stratified four-axis permutation/BH family, deterministic
  bootstrap intervals, and refit ablations. Table 2e rows remain source-cohort
  context and never become sample pathway or categorical subtype calls.
- `kncc-gbm-longitudinal-concordance/1.0.0`: a source-locked protein-transition
  model fitted from 104 strict PDC000514 primary/recurrent GBM pairs, with honest
  patient-grouped nested cross-validation, bound-aware robust inference,
  coupled measurement/coefficient uncertainty, source-processing and driver
  ablations, and exact heteroscedastic-Huber PELT segmentation.
- `kncc-paired-phosphosite-transition/1.0.0`: a source-locked phosphosite
  transition model fitted from 88 strict PDC000515 primary/recurrent GBM pairs,
  with nested grouped evaluation, exact full-refit bootstrap perturbations,
  composite-site preservation, assay attestation, uncertainty decomposition,
  support suppression, and fail-closed maturity gates; and
- `kncc-gbm-longitudinal-kinase-transition/1.0.0`: a source-locked comparison of
  PDC000515 longitudinal phosphosite transitions with the fixed 24-hypothesis
  SPHINKS signature family. It uses training-only grouped evaluation,
  residue/cardinality-stratified competitive nulls, fixed-family BH FDR,
  inverse-multiplicity correction, composite preservation, and patient-bootstrap
  uncertainty. It is signature concordance only, remains LIMITED, and is not
  biochemical/causal kinase activity or evidence independent of PDC000515; and
- `kncc-reactome-conditional-transition/1.0.0`: a fitted global-plus-conditional
  protein-transition model over a fixed, repository-authored 10-event Reactome
  V97 glioma panel and 104 strict PDC000514 pairs. It uses training-only robust
  source effects, eight held-patient folds, five held-gene folds, degree-aware
  global residualization, bound-aware ridge IRLS, 256 patient-bootstrap source
  fits, request-specific reconstruction gates, and structural ablations. Its
  output is membership concordance rather than pathway activation or flux, and
  overlap-confounded PI3K/AKT evidence can never be fully supported.
- `kncc-reactome-complex-transition/1.0.0`: 28 separately fitted,
  missing-aware robust rank-one protein-transition factors over exact Reactome
  V97 participant sets in 11 repository-authored pilot domains. The panel was
  informed by public glioma biology and the PDC000514 source paper and selected
  without reading abundance arrays during import; it is not demonstrated
  outcome-independent. The model uses 104 strict
  PDC000514 pairs, eight patient-grouped held-member evaluation folds, 128
  patient-bootstrap source fits, censor-aware runtime projection, and explicit
  source-processing, loading, member, and overlap ablations. Its output is
  participant-set transition concordance, not assembly, activity,
  essentiality, stoichiometry, causality, or clinical prediction.
- `kncc-neftel-program-transition/1.0.0`: a fitted global-plus-conditional
  protein-transition model over the exact eight Neftel Table S2 program marker
  sets and 104 strict PDC000514 primary/recurrent GBM pairs. It uses
  patient-grouped outer folds, held-marker evaluation, deterministic Huber
  IRLS/ridge inference, 128 patient-bootstrap refits, one-sided censoring, and
  measurement/source/topology ablations. Its fitted dictionary beats the
  global-only comparator but loses to equal marker membership, so every
  numerical runtime coordinate is capped `LIMITED`. It is bulk-protein
  same-cohort transition concordance, not single-cell state, cellular fraction,
  recurrence prediction, tumor evolution, or clinical evidence.

The additional `glio-ecgi-kncc-gbm-transition/1.0.0` factor-graph surface is not
a thirteenth independent fitted model. It runs the exact PDC000514 Reactome and
PDC000515 SPHINKS signature-transition child engines numerically independently
but deterministically in serial, nests their exact receipts, and adds only a
locked 41-node presentation topology with 39 annotation-only containment edges
and zero numerical cross-block edges. It performs no cross-modal fusion or
feedback and therefore does not increase the twelve-lane independent-inference
count. See
[`kncc-gbm-factor-graph.md`](kncc-gbm-factor-graph.md).

Two exact-source CPTAC GBM implementations are tracked separately from that
mounted inventory: `cptac-gbm-cis-dosage/1.0.0` and
`cptac-gbm-transcript-protein-discordance/1.0.0`. Both provide real local
fit/query/replay algorithms over caller-owned exact source copies, but neither
bundles a fitted artifact or mounts an HTTP route. A caller-built artifact is
therefore local cohort evidence, not a repository-shipped model, and neither
implementation increases the twelve-lane mounted count.

These lanes remain research-only. Their presence does not promote any governed
module or establish clinical validity.

## Published GBM RNA-purity replacement

The additive `gbm-rna-tumor-purity/1.0.0` lane now replaces caller-declared or
hash-derived purity-like behavior with the exact fitted GBMPurity neural model
for its narrow intended population. It consumes raw bulk RNA counts, not
protein evidence, and emits one malignant-cell-fraction estimate—not immune
composition. Exact PyTorch/NumPy parity, source-tree admission, coverage gates,
local numerical attribution, API/CLI replay, and claim ceilings are documented
in [`gbm-rna-purity.md`](gbm-rna-purity.md).

This does not complete M14 microenvironment replacement. A licensed,
donor-aware GBM single-cell reference and count-native mixture model are still
required for multi-lineage fractions.

The fixed CC BY 4.0 GBmap Zenodo artifact is now conditionally admitted as the
preferred offline fitting source. Its approximately 9 GB source bytes have not
been downloaded, SHA-256 hashed, or fitted in this checkout. A source-independent
core now implements exact pseudobulk aggregation, fold-local stable-marker
selection, leakage-safe whole-study and within-study donor validation plans,
donor/study-shrunk Dirichlet-multinomial fitting, adaptive-unknown simplex
inference, calibrated mismatch diagnostics, and an end-to-end training-only
candidate-selection protocol with equal validation-family weighting. Its fail-closed
development profile records `fit_state="development_unfitted"`, binds those
semantics, and forbids model, artifact, runtime, HTTP, CLI, and `SUPPORTED`
availability. The 109-versus-110 conflict is now source-locked: final Table S1,
all CELLxGENE versions, and the original preprint support 110 source donor
categories, while only the final paper prose says 109. A byte-range audit of
the authoritative Zenodo H5AD additionally found 113 raw patient categories and
17 raw author batches. The offline extractor now locks the legacy HDF5/CSR
layout, exact 20-label vocabulary, a 17→16 study crosswalk, two-pass file
integrity, checked count aggregation, and deidentified receipts. It refuses to
fit unless the digest-bound 113→110 donor crosswalk is supplied. That crosswalk
now groups the three source PW032 samples to PW032 and, from the original Pombo
patient table and reporting summary, groups the distinct `R4` and `R4 n.c.`
source samples to donor R4. Raw categories are never treated as independent
donors merely to make training proceed. Exact source SHA-256 verification,
extraction, fitting, and held-out calibration remain. The redistribution
boundary, validation gates, and remaining blockers are recorded in
[`gbmap-deconvolution-source-admission.md`](gbmap-deconvolution-source-admission.md).
No fitted artifact or runtime endpoint exists for this candidate, so it does
not increase the twelve-lane fitted-inference inventory.

## Local M07 cis-dosage substitution boundary

`m07-cptac-gbm-cis-dosage-cohort-evidence/1.0.0` now provides an exact local
facade over the fitted `cptac-gbm-cis-dosage/1.0.0` lane. It identifies only
M07-04's scalar-copy/interval-midpoint declaration proxy as eligible for
cohort-evidence substitution. The delegate is a genuine fold-local Huber-IRLS
CNV-to-RNA-to-protein model over exact CPTAC GBM sources, but it remains a
gene-level cohort query rather than a patient posterior or causal mediation
model. Unverified supplement redistribution terms require a same-user local
artifact and structurally forbid a public HTTP mount. M07-05 mechanism
integration and M07-06 uncertainty decomposition remain out of scope. See
[`m07-cis-dosage-facade.md`](m07-cis-dosage-facade.md).

## Source-locked phosphosite runtime lane

`kncc-paired-phosphosite-transition/1.0.0` is now fitted from 88 strict
PDC000515 primary/recurrent pairs as a separately source-locked phosphosite
concordance axis. It preserves composite site groups, technical repeats,
missingness, nested patient-grouped evaluation, bootstrap uncertainty, and an
exact SPHINKS peptide/site crosswalk. It is packaged, integrity checked, and
mounted as a stateless API/CLI/workbench lane with exact replay. Protein
adjustment, occupancy, kinase inference, and cross-assay fusion remain
explicitly `not_fitted`; see
[`longitudinal-gbm-phosphosite-foundation.md`](longitudinal-gbm-phosphosite-foundation.md).

## Source-locked signature-transition lane

`kncc-gbm-longitudinal-kinase-transition/1.0.0` is mounted as an additive
API/CLI lane, not as a replacement for the raw-phosphosite axis. Its fully
training-only five-fold held-pair evaluation recovered 68/88 directions versus
70/88 for the raw phosphosite comparator on the same folds. Signature-only and
raw-only correct counts were 7 and 9 (exact McNemar `p=.804`), so it does not add
independent evidence. Eleven of 12 selected signatures pass the frozen
bootstrap selection threshold; CHEK2 is explicitly unstable. Full-set bootstrap
stability and interval-calibration gates fail, forcing every estimable runtime
output to LIMITED. See
[`longitudinal-gbm-kinase-transition.md`](longitudinal-gbm-kinase-transition.md).

## Compatibility facades, not new inference lanes

Five API-only v2 facades expose existing fitted research evidence at explicit
module integration boundaries:

- the M09 complex-transition facade delegates participant-set transition
  scoring, uncertainty, ablations, and replay to the fitted PDC000514/Reactome
  factor lane, replacing only participant-transition numerical stand-ins and
  never emitting assembly, stoichiometry, essentiality, or activity;
- the M10 functional-proteotype facade delegates numerical scoring, uncertainty,
  ablations, and replay to the source-locked Migliozzi four-axis bulk-protein
  model, replacing only synthetic or caller-declared numerical stand-ins as
  research evidence;
- the M11 protein-native subtype facade delegates numerical scoring and replay
  to the exact published GBM proteomic-axis lane; and
- the M14 microenvironment protein-program facade delegates numerical scoring
  and replay to the Neftel bulk-protein program lane.
- the M15 longitudinal-recurrence facade delegates transition scoring,
  uncertainty, ablations, optional change-point analysis, and replay to the
  fitted KNCC/PDC000514 longitudinal protein model.

They add responsibility/exclusion metadata and compatibility transport, not new
scientific models, posterior subtype/cell-fraction estimates, or independent
evidence. They therefore do not increase the twelve-lane inference count.

## Strict numerical-stand-in floor

At the 2026-08-29 source snapshot, M06 through M20 contain 120 provisional
packages. M06 through M15 contain 80 packages. An exhaustive static audit of
those 80 identifies 22 engines with unmistakable numerical stand-ins:

```text
M06-04
M07-04 M07-05
M08-03 M08-04 M08-05
M09-03 M09-04 M09-05 M09-06
M10-03 M10-07
M11-05 M11-06
M12-05
M13-03 M13-05 M13-06
M14-03 M14-05
M15-04 M15-05
```

The strict union contains nine digest-derived-number engines, six fixed-posterior
engines, three mean or weighted-blend engines, four declaration/no-model
scientific engines, and one sine-wave fixture estimator; categories overlap.
Examples include SHA-256 bytes used as a complex or pathway score, fixed
posterior intervals, caller-declared state returned with posterior mass `1.0`,
and M10-03's `sin(index + 1) * 0.1` fixture with fixed `0.95` support and a
fixed-width interval. M11-06 hashes an upstream digest and declared perturbation
into a response with a fixed uncertainty envelope.

The strict 22 are a floor for counterfeit estimators, not the whole scientific
debt inventory. Twelve further engines are transparently labelled
formula/pass-through/declaration shells rather than fitted models: M06-03,
M10-05, M11-03, M11-04, M12-03, M12-04, M12-06, M13-04, M14-04, M14-06,
M15-03, and M15-06. Three representation constructors—M07-02, M08-02, and
M09-02—also synthesize numeric vectors from hashes. They remain classified as
representation plumbing, but their vectors must never be described as learned
biological features. The exhaustive partition is therefore 22 strict stand-ins,
12 transparent scientific shells, three synthetic representation constructors,
and 43 schema, safe-abstention, validation, registry, evidence-publisher, or
other non-estimator engines.

The strict list deliberately excludes representation/schema plumbing, safe
abstention, lineage services, and M16 through M20 workflow duties. Those
surfaces may be scientifically incomplete without being counterfeit
estimators. The broader partition above keeps synthetic representations visible
without relabelling workflow metadata as biological inference.

Governed contracts and digests are preserved while replacements are developed as
new research lanes. A provisional route must not be silently relabeled as mature
or redirected to a different algorithm.

## Completed replacement

The first priority is now implemented as the additive KNCC research lane. It
does not alter or silently redirect the frozen governed longitudinal contracts.
Its output is deliberately named source-cohort protein concordance rather than
tumor evolution, and its nested held-pair performance is internal source-cohort
evaluation rather than external validation.

The M10 functional-proteotype scientific replacement is also implemented as the
additive `migliozzi-gbm-functional-proteotype/1.0.0` lane. It uses exact licensed
aggregate Table 2d/2e evidence and a real constrained estimator rather than the
governed M10-03 sine-wave fixture or M10-07 digest-derived score. The governed
M10 routes, schemas, digests, and placeholder implementations remain visible
technical debt and are not silently redirected or relabeled as mature. The
research/v2 M10 compatibility facade now exposes the fitted model at the module
boundary with explicit per-responsibility exclusions; it is not a governed
replacement and does not convert concordance coordinates into pathway activity,
mechanism, prognosis, or treatment claims. See
[`gbm-functional-proteotype.md`](gbm-functional-proteotype.md).

## Negative cross-assay feasibility result

An exact development-only join found all 88 PDC000515 pairs in PDC000514, but
the assay-specific reference UUID sets had zero overlap and therefore cannot be
pooled or interpreted as occupancy. In leakage-safe 5x3 patient-grouped nested
cross-validation, the protein model recovered 71/88 held-pair directions, the
phosphosite model 66/88, and nested late fusion 67/88. Fusion-only and
protein-only correct calls were 2 and 6 respectively (exact McNemar `p=.289`).
The fusion candidate therefore supplied no held-pair evidence beyond protein
alone and remains `not_fitted`. This is a negative feasibility audit, not release
validation, and it removes late fusion from the active replacement queue.

## Completed Reactome conditional-transition model

`kncc-reactome-conditional-transition/1.0.0` is now a fitted, mounted API/CLI
research lane rather than a source-admission placeholder. Its compact source
catalog locks the exact PDC000514 protein feature axis, a pre-outcome ten-event
Reactome V97 glioma-domain panel, nearby nonselections, parent/source hashes,
deterministic patient/gene/pathway order, and exact membership indices. The
fitted artifact adds a 1,872-gene global-plus-conditional design and 256
patient-bootstrap source fits without bundling patient values, identifiers,
identifier-derived hashes, scores, residuals, fold membership, or bootstrap
resample indices.

All source statistics and loadings are refit inside eight held-patient folds;
five held-gene folds within each patient produce 520 reconstruction evaluations.
The joint dictionary's median standardized MAE is 0.5554163035 versus
0.5622984198 for the global-only model, a modest median relative improvement of
1.20459348%. All ten individual cohort leave-pathway-out q05--q95 intervals
cross zero, so runtime pathway coordinates require strict request-specific
support and remain conditional concordance—not activation, flux, causality, or
clinical evidence. This was the tenth real inference lane when completed. See
[`kncc-reactome-conditional-transition-source.md`](kncc-reactome-conditional-transition-source.md)
and
[`kncc-reactome-conditional-transition-model.md`](kncc-reactome-conditional-transition-model.md).

## Completed Reactome participant-set transition model

`kncc-reactome-complex-transition/1.0.0` adds a separate fitted view of the
same PDC000514 protein cohort. Its source catalog locks a prespecified
repository-authored pilot panel of 28 exact Reactome V97 participant sets across
11 explicitly pilot domains, informed by public glioma biology and the source
paper. Selection does not read abundance arrays during import, but the panel is
not demonstrated outcome-independent. The catalog also locks exact
UniProt/HGNC/PDC feature projections, direct pathway bindings, nesting,
same-family overlap, inverse membership degree, and leave-family-out metadata.
The fitted artifact contains 28 separate missing-aware rank-one Huber models,
146 member slots over 120 unique proteins, and 128 patient-bootstrap loading
fits without bundling patient values, identifiers, fold assignments,
coordinates, predictions, residuals, or resample indices.

Eight patient-grouped outer folds produce 14,988 held-member reconstructions.
Mean standardized MAE is 0.6989814224 versus 0.8769685109 for the training-center
baseline and 0.9407301748 for zero transition; direction accuracy is
0.7255137443. The patient-cluster median relative gain is 0.1489483703, with a
nominal 90% interval of [0.0990936656, 0.1805654575]. All preprocessing,
factor, and evaluable coordinate fits converge, while 56 held coordinates
abstain for insufficient remaining member support. This is internal
source-cohort reconstruction, not external validation.

Runtime preserves exact and one-sided-censored transition evidence, solves a
real Huber-ridge coordinate against each fitted loading, separates measurement
and fitted-source bootstrap sensitivity, and reports source-processing,
signed-uniform-loading, top-member, and same-family-overlap ablations. Its
strict ceiling is participant-set protein-transition concordance—not complex
assembly, biochemical activity, essentiality, stoichiometry, causal mechanism,
clinical state, or treatment response. This lane raises the current independent
inference inventory from ten to eleven. See
[`longitudinal-gbm-complex-transition.md`](longitudinal-gbm-complex-transition.md).

## Completed KNCC/Neftel conditional-transition model

`kncc-neftel-program-transition/1.0.0` adds a second fitted view of the exact
PDC000514 protein cohort, bound to the exact Neftel Table S2 MES2, MES1, AC,
OPC, NPC1, NPC2, G1/S, and G2/M marker identities. The source projection maps
289 union markers before eligibility and fits a fixed 256-feature union across
104 strict matched primary/recurrent patient groups. The artifact contains one
global loading, eight conditional program loadings, eight patient-grouped outer
folds with five held-marker folds, and 128 patient-bootstrap refits without
shipping patient values, identifiers, identifier-derived hashes, scores,
residuals, fold assignments, or bootstrap indices.

The joint dictionary's median standardized held-out MAE is 0.5754778047 versus
0.6039095267 for global-only and 0.5177467313 for equal marker membership. Its
patient-cluster median relative gain over global-only is 0.0248465156 with a
nominal 90% interval of [0.0153265550, 0.0380342956], while its gain relative to
equal membership is -0.0987176386 with [-0.1155036986, -0.0777444485]. All
eight leave-program-out intervals cross zero. That negative comparator result
is retained as a release gate: the runtime computes the fitted coordinates but
caps every estimate `LIMITED`, and abstains when exact evidence or reliability
support is inadequate. This is the twelfth real inference lane. See
[`longitudinal-gbm-neftel-transition.md`](longitudinal-gbm-neftel-transition.md).

## CPTAC GBM cis-dosage local-only implementation

A read-only, exact-hash audit of the CPTAC GBM Table S2 workbook established a
scientifically defensible **local-build** path for gene-level cis-dosage
evidence, but not authority to bundle a fitted coefficient artifact. That path
is now implemented as the local-only `cptac-gbm-cis-dosage` CLI with
`fit-local`, `profile`, `analyze`, `verify`, and `verify-source` commands, plus a
stateless library query over caller-built artifacts. It has no public
HTTP route and is not an additional mounted inference lane. Exact
one-to-one HGNC mapping produced 10,430 genes across CNV, RNA, and protein for 96
patient groups; 9,457 genes passed complete five-fold patient-grouped
out-of-fold support. Across supported genes, median held-out RNA-from-CNV R²
was 0.0668 and protein-from-CNV+RNA R² was 0.2188. Protein prediction improved
over CNV-only by median R² 0.1776 but did not improve over RNA-only genome-wide
(median delta R² -0.0060); 334 genes passed the stricter joint/sensitivity
screen. Table S3 flags were used only as post-hoc same-cohort concordance and
their zeros were not treated as negatives.

This is a completed local implementation, not an additional shipped HTTP
inference lane. Until supplement redistribution/derived-artifact terms are admitted, the
implemented product remains a same-user exact-source local builder plus a local,
stateless gene-level evidence query. It never persists sample headers, fold membership,
patient-level predictions, or identifier-derived hashes, and its observational
standardized decomposition cannot be called causal mediation. See
[`cptac-gbm-iprofun-foundation.md`](cptac-gbm-iprofun-foundation.md).

An exact iProFun R-oracle reproduction and permission to redistribute a fitted
public artifact remain future source-admission work; neither is implied by the
local implementation.

## CPTAC GBM transcript–protein conditional-association local implementation

`cptac-gbm-transcript-protein-discordance/1.0.0` now provides a second
exact-source local-build path over the 96 resolved patient groups and 10,430
CNV/RNA/protein genes in CPTAC GBM Table S2. For one through 256 predeclared
genes, it compares five-fold, fold-local Huber-IRLS
`Protein ~ RNA + CNV` predictions with RNA-only, CNV-only, and training-median
comparators. It reports common-support held-out R², Spearman correlation, MAE,
residual MAD, both incremental-R² ablations, and raw-scale conditional RNA
coefficient stability. Each accepted gene also receives 128 deterministic,
fold-stratified patient-bootstrap full refits and nominal 90% nearest-rank
intervals.

This is an implemented fitter, aggregate artifact, local query, and exact replay
contract—not a bundled fitted cohort artifact. The repository therefore makes
no source-derived gene-performance or biological-validation claim for this lane.
The local runtime accepts artifact and gene identifiers only; patient
measurements, OOF arrays, patient identifiers or hashes, fold membership, and
residual vectors cannot cross the artifact/query boundary. No HTTP route is
mounted, and supplement redistribution remains `local_only_terms_unverified`.

Every estimable gene is capped `LIMITED`. Positive and inverse labels mean only
that nominal source-cohort intervals support a conditional RNA coefficient and
incremental prediction over CNV-only. They are not biological buffering,
causal mediation, a patient prediction, or an iProFun result. The repository's
zero-boundary rule has no genome-wide multiplicity calibration or independent
validation. The governed M08 v1 routes, schemas, digests, and provisional
M08-03/M08-04/M08-05 engines remain unchanged and remain in the stand-in debt
inventory. See
[`cptac-gbm-transcript-protein-discordance.md`](cptac-gbm-transcript-protein-discordance.md).

## Prioritized replacement queue

1. **GBM microenvironment inference.** Use an explicitly licensed GBM single-cell
   reference and count-native Bayesian mixture method for RNA fractions. A
   protein-only projection may report program concordance but must abstain from
   cell-fraction claims.
2. **Broader GBM complex/pathway evidence graph.** The source-locked PDC000514
   participant-set transition lane now supplies a real protein-only complex
   component, but it does not complete a multimodal pathway graph. Replace the
   remaining synthetic demo topology with a versioned Reactome graph and a
   source-admitted matched PDC000204/PDC000205 protein/phosphosite cohort. A
   read-only byte audit found the same 110 unique non-pool aliquot labels in the
   same order across both assay maps and matrices, but this is not yet a patient
   join: the local bundle has no PDC000205 study/version record, no file-level PDC
   provenance, and no official case/specimen map. The separate PDC000204
   metadata reports 111 cases/aliquots, which is unresolved against the 110
   captured labels. The next lane is therefore design-only and admission-blocked;
   it must learn edge-family reliability inside nested case-group folds while
   retaining the real robust ECGI solver, explicit topology/modality ablations,
   and an internal-concordance-only ceiling. Exact byte locks, grouping,
   endpoints, leakage controls, gates, and blockers are specified in
   [`cptac-gbm-matched-evidence-graph-design.md`](cptac-gbm-matched-evidence-graph-design.md).
3. **Glioma immunopeptidomic presentation.** Bind exact HLA alleles and pinned
   pretrained processing/binding/presentation models, with allele support,
   calibration, and abstention exposed in every result.

The lower-risk M11 integration is complete: its research/v2 facade delegates to
the exact published GBM proteomic-axis ensembles without changing the frozen
governed M11 route. It remains a compatibility surface, not another model or a
scientific substitute for the replacement work above.

Each replacement must provide `profile`, synthetic `demo`, `analyze`, and exact
`verify` operations; immutable source and profile digests; strict typed missing and
censored states; uncertainty and ablations; source-derived or independently
calculated oracles; and non-prescriptive claim ceilings.

## Source-admission rule

A public URL is not a redistribution license. Raw workbooks, trained objects, or
third-party annotations are vendored only when their reuse terms are explicit and
compatible. Otherwise the repository may provide a hash-verifying user-side
importer, or the model remains permission-gated. Patient-level matrices are never
bundled merely because they appeared in supplementary material.
