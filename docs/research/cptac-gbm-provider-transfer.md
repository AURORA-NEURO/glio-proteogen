# CPTAC GBM raw-assay provider-transfer stress benchmark

This method specification is frozen before the first external performance run.
The run uses profile
`cptac-gbm-raw-assay-provider-transfer-stress/1.0.0`. It trains on the fixed
72-candidate discovery source plan and scores the fixed 56-candidate
confirmatory plan after strict local source admission. These are metadata
candidate inventories, not publication-wide patient counts or newly verified
clinical populations. Source admission and source-only training can proceed
while reference-material evidence is reviewed. External scoring must wait
until this policy, its implementation, source bindings, and synthetic tests
are frozen.

The benchmark asks whether a discovery-trained model reconstructs the same
gene's provider-reported protein coordinate in a different acquisition and
processing setting, and whether adding RNA to CNV improves that reconstruction.
Negative transfer is an allowed result. This is a computational research
question, not a claim of novel glioma biology, causal regulation, clinical
prediction, or AlphaFold-scale capability. It neither changes nor admits the
old Table S2 estimator, source locks, artifact format, or evidence gates.

## Design history and fixed panel

The sixteen genes remain fixed:

```text
CDK4 CDKN2A CDKN2B EGFR IDH1 MDM2 MDM4 NF1
PDGFRA PIK3CA PIK3R1 PLCG1 PTEN PTPN11 RB1 TP53
```

Their literature rationale comes from the
[Wang et al. CPTAC study](https://pmc.ncbi.nlm.nih.gov/articles/PMC8044053/)
and [Brennan et al. TCGA GBM study](https://pmc.ncbi.nlm.nih.gov/articles/PMC3910500/).
Total gene-level protein measurements do not reproduce phosphorylation-site
activation findings. IDH1 expression does not establish IDH mutation status.
Keep all sixteen genes in every receipt, including structural absences and
abstentions; do not substitute better-covered genes.

The development history includes earlier source-cohort model comparisons and
inspection of confirmatory protein availability. The external support policy
is therefore coverage-informed. At this specification's preparation, external
RNA/protein relationships and model-prediction errors have not been used to
choose the loss, predictors, solver budget, or selection rule. Prespecification
applies to those future scores; it does not make the panel independent of
published study knowledge or erase earlier development decisions. Freeze the
protocol before the first external prediction metric and retain every result.
Changing MAE to squared error after seeing a gene's outcome requires a new,
explicitly exploratory analysis, not a replacement primary analysis.

## Source coordinates and what is actually aligned

Use exact, checksum-bound PDC000204 discovery and PDC000446 confirmatory CDAP
protein assemblies and their official channel maps, paired to the frozen open
GDC files through the strict specimen-level plans. Use the same fixed approved
HGNC snapshot and exact stable identities in both cohorts. These inputs are
provider-processed assay outputs; the word "raw" distinguishes them from the
publication's joint harmonized/imputed matrices, not from mass-spectrometer
reporter intensities or sequencing reads.

| Assay | Selected coordinate | Preserved distinction |
| --- | --- | --- |
| Protein | CDAP `Unshared Log Ratio`: median-normalized log2 specimen/common-reference ratio | All-peptide ratios never fill unshared blanks; these are relative, not absolute abundances. |
| RNA | STAR `fpkm_uq_unstranded`, declared GENCODE v36 schema | Counts, TPM, FPKM and FPKM-UQ are different coordinates; no `log1p` or external renormalization is introduced. |
| CNV | AscatNGS integer total `copy_number` | Neither GISTIC scores nor log2 segment means; no conversion to either is attempted. |

The [PDC analysis guide](https://pdc.cancer.gov/pdc-docs/data-analysis-guides)
defines the two peptide families and explains that report summary rows precede
median normalization. The selected gene values must not be replaced by those
summary rows. The [GDC RNA workflow](https://docs.gdc.cancer.gov/Data/Bioinformatics_Pipelines/Expression_mRNA_Pipeline/)
defines FPKM-UQ using the broader expression gene set; this benchmark preserves
that supplied normalization and does not recompute it from the sixteen genes.
The [GDC CNV workflow](https://docs.gdc.cancer.gov/Data/Bioinformatics_Pipelines/CNV_Pipeline/)
defines total gene copy number and entirely blank gene triplets. A shared
column name or matching gene coordinate does not prove processing identity.

### Evidence found before scoring

The version-specific official PDC protocol/workflow queries and a bounded GDC
query for every selected RNA/CNV file are captured privately, with exact query,
raw response, canonical response and SHA256 bindings. Public field definitions
and version-selection rules are in the
[PDC API documentation](https://pdc.cancer.gov/pdc/publicapi-documentation/)
and [GDC API documentation](https://docs.gdc.cancer.gov/API/Users_Guide/Search_and_Retrieval/).

| Processing declaration | Discovery | Confirmatory |
| --- | --- | --- |
| Protein protocol | TMT11, MS2 | TMT11, MS2 |
| CDAP report version | `CPTAC3-1.1.17` | `CPTAC3-1.2.1` |
| Database search declaration | `MSGF+ v2017.01.27` | `MSGF+ v2017.01.27` |
| Gene-to-protein mapping declaration | `2018-08-10` | `2018-08-10` |
| RefSeq file declaration | `RefSeq.20180629_Human_ucsc_hg38_cpdbnr_mito_264contams.fasta` | `mixed_human_broad-cptac-refseq-human+contaminants_20180629.fasta` |
| STAR workflow commit declarations | `122a0dd1445b2664b1b40b7df7b0e2240183d712`, `5d8c131bbff59fb0c969217fc1d44e6d1503cd1f` | Those two plus `eecca6e2e475aab335bd7c365025ca0d0daa144b` |
| AscatNGS workflow commit declarations | `d82167c739cd97869f77998d5ab175b70a1850ee` | That commit plus `24db0854fc8f555ad7925ebf9a6c020a4b1ef019` |

Workflow commit identifiers are not software semantic version numbers. Similar
RefSeq dates do not prove identical sequence databases. The captured protocol
`internal_standards` fields are null and workflow HGNC-version fields are blank.
The exact CNV gene annotation release remains unadmitted; neither RNA's GENCODE
header nor gene-coordinate agreement identifies it. Record absent metadata
explicitly rather than completing it by inference.

Both primary papers describe a channel-126 pooled tumor/normal reference.
[Liu et al.](https://pmc.ncbi.nlm.nih.gov/articles/PMC11337243/) also describe
additional cross-cohort ComBat alignment and DreamAI processing. Their joined
publication matrix is therefore excluded from an untouched provider-transfer
test. These descriptions do not establish that the two admitted CDAP files
used the same physical reference lot. The
[PDC authors' repository paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC11413857/)
identifies cross-dataset reference differences as a general comparability
problem; it does not establish which physical reference this particular pair
shared.

Keep three distinct conclusions in the processing-boundary receipt:

1. An equal POOL case/sample/aliquot identifier is an issuer's metadata linkage.
   It supports reference-record correspondence, not independently audited
   material composition, preparation, lot, storage history or calibration.
2. Lack of observed tumor case/sample/aliquot overlap is a metadata exclusion
   audit. It is not genotype-based donor matching or proof of donor independence.
   A shared reference is not an extra independent patient observation.
3. Complete processing identity is not established: CDAP declarations differ
   and GDC workflows are mixed. Common numerical coordinates do not remove
   reference, laboratory, annotation, specimen-composition or processing shifts.

For this run the explicit estimand is **unharmonized provider-transfer stress**.
Its numerical loss is well-defined on the delivered protein ratios, conditional
on both source processing systems. It measures their combined acquisition,
reference and biological differences; it cannot attribute a loss change to
biological failure or successful biological transport alone. Processing
differences do not make this stress experiment meaningless or automatically
block source-only fitting.

A future *aligned* transport profile would need separate, explicit evidence
about reference material/equivalence or a validated independently calibrated
bridge, annotation/sequence mappings, normalization and workflow differences.
Any bridge must be frozen without target prediction outcomes; learning a
target protein intercept from this test set is recalibration, not untouched
testing. Such a profile must receive a different versioned identifier and
cannot retrospectively relabel this stress run as biological validation.

## Observation units and complete-case estimand

Each frozen plan supplies one observation per distinct metadata case group and
an exact same-specimen protein/RNA/CNV assignment. Nonunique ancestry,
replicates and unresolved roles remain withheld. Clinical class, treatment
timing, purity, site effects, molecular WHO eligibility and genetic donor
independence require separate evidence; the benchmark does not infer them
from expression. Historical GBM labels cannot silently become a verified pure
WHO CNS5 IDH-wildtype cohort.

For gene `g`, define complete support separately in each cohort as observations
with finite RNA, CNV and selected unshared protein values. Numeric zero is
observed. A present protein row with blank cells differs from a structurally
absent feature; ambiguous or unresolved identities remain unavailable. Do not
impute measurements, borrow all-peptide values, or drop difficult rows after
seeing prediction errors.

The target is the empirical reconstruction loss among these admitted,
jointly observed cases. This conditions on assay availability, including
protein availability, and can select a nonrepresentative subset. It does not
estimate performance for missing-protein patients, all gliomas, future sites,
or an intervention. Complete-case validity does not imply missing-at-random.
All four fixed families and the selected policy must use the exact same
external cases for each gene; different genes may have different supports.

## Frozen source fitting and training-only selection

Candidate order is `training_median`, `rna_only`, `cnv_only`, `full`:

```text
training_median: median source-training Protein
rna_only:       Protein ~ intercept + RNA
cnv_only:       Protein ~ intercept + CNV
full:           Protein ~ intercept + RNA + CNV
```

Assign the source case keys to five folds before gene filtering: sort by the
raw SHA256 digest of `case_submitter_id.encode("utf-8")`, break a digest tie by
the exact case string, then assign sorted positions modulo five. Restore the
plan's original row order when attaching folds. Keys are unique and
source-only; external identifiers, expression values, target losses and
outcome stratification never enter this rule. Keep individual keys/folds
private and bind only the complete assignment's aggregate digest.

The source nested evaluation retains the existing necessary gates: at least
48 complete outer-training cases, three complete held-out cases, four valid
outer folds and 60 common source OOF observations. Inside an outer training
set, its four remaining fold labels form four inner validation blocks, each
requiring 32 complete inner-training and three inner-validation cases. Use
the same complete rows for all candidates. Each candidate needs finite
predictions covering every inner validation case; a failed candidate is
excluded, not allowed a smaller scoring subset. Pool individual absolute
errors across blocks; do not average unequal block MAEs. Exact MAE ties prefer
median, RNA, CNV, then full. Insufficient inner support produces an explicitly
labelled training-median fallback, not a claimed MAE winner. An outer refit
failure also uses a training-only median fallback for the selected-policy
diagnostic, with the failure visible.

This new stress profile adds a stricter final-selection gate: every fixed
candidate must provide finite source OOF predictions for **every** joint
complete source case across all five folds. Necessary nested support gates
still apply. An incomplete candidate or fold causes stress abstention rather
than selection on reduced or unequal source support. Undefined source nested
metrics, including a degenerate median-reference denominator, remain a source
failure under the existing nested procedure.

After those source-only gates pass, choose the final candidate using pooled
all-source fivefold OOF MAE on that complete common support, with the same exact
tie order. This final choice is distinct from the outer-fold choices used to
evaluate the nested policy. Refit **all four** fixed families using all
source-complete cases; require finite, converged fits before external scoring.
Freeze their transforms and parameters. The selected external predictor is
the selected member of these frozen fits, not an average or vote among
outer-fold winners. A failed final refit causes abstention; it is not replaced
after looking at external error.

Nested assessment separates internal evaluation from model selection, as
motivated by [Varma and Simon](https://doi.org/10.1186/1471-2105-7-91) and
[Cawley and Talbot](https://www.jmlr.org/papers/v11/cawley10a.html). It does not
undo source-informed development or establish calibrated external inference.

### Fixed 240-iteration numerical equations

Use the existing bounded adaptive-scale solver from
`cptac_gbm_transcript_protein_discordance/convergence.py` with exactly 240
iterations; do not change the legacy 30-iteration profile. For each variable
in a particular training fit, set its center to its training median and its
scale to `1.4826 * median(abs(value - median(value)))`. If that scale is
nonfinite or below `1e-8`, use training sample SD (`ddof=1`); reject an
unusable fallback. Standardize response and included predictors with these
training values only. At prediction time, invert the response transform with
the same frozen training center and scale. External values never set scales,
centers, cutoffs, winsorization, model families, slopes or intercepts.

Let `Z` be the standardized predictors with an intercept, `t` the standardized
response and `P = diag(0, 1e-8, ...)`. Initialize
`b = solve(Z.T @ Z + P, Z.T @ t)`. At each iteration:

```text
r = t - Z @ b
s = 1.4826 * median(abs(r - median(r)))
w_i = 1                              if abs(r_i)/s <= 1.345
      1.345 / (abs(r_i)/s)            otherwise
b_new = solve(Z.T @ diag(w) @ Z + P, Z.T @ diag(w) @ t)
```

If finite `s < 1e-8`, accept the current coefficients as converged. Otherwise
accept `b_new` when `max(abs(b_new - b)) < 1e-8`; a failed solve, nonfinite
value, degenerate required scale or exhausted iteration budget remains an
explicit failure. The intercept is not ridge-penalized. Adaptive residual-MAD
updates describe a fixed iterative procedure, not proof of descent of one
fixed convex objective or of a global optimum. Ridge-assisted prediction does
not identify a separate biological RNA effect under collinearity. Report no
naive conditional slope p-values or pooled coefficient for a selected policy.

## External support and predeclared endpoints

The external minimum is **48 jointly complete case groups per gene**. This is
a distinct, coverage-informed design policy for scoring fixed predictors,
not a validated precision threshold or a relaxation of a legacy fitting gate.
The confirmatory cohort does not itself need 60 training OOF observations:
it performs no training or fold selection. Below 48, retain counts and a
structured abstention without a fallback 30-case performance analysis.

Predictions must be finite for every externally complete case and every fixed
family before comparison. Do not silently shrink support for one model.
External labels are used for scoring after freezing the source fits; no
centering, calibration, feature selection, batch correction or refitting uses
them. Report median, RNA-only, CNV-only, full and selected-policy metrics on
the same exact support, including poor and negative results.

The primary paired endpoint is
`mean(abs(Protein - full) - abs(Protein - CNV-only))`.
Negative values favor adding RNA; positive values favor CNV-only. The
secondary policy endpoint is
`mean(abs(Protein - selected) - abs(Protein - full))`, where negative favors
the source-selected policy. Keep all sixteen predeclared genes visible and
the two endpoints distinct. The profile emits no discovery p-values, FDR calls
or clinical significance labels; nominal per-gene intervals do not provide
simultaneous coverage across genes or endpoints.

For all five predictors also report MAE, RMSE, and the explicitly named
`R2_vs_source_training_median = 1 - SSE_model / SSE_source_median` on the
same external cases. The median is the frozen all-source-complete protein
median, not an external mean or refitted intercept. Preserve negative values.
If the denominator is nonfinite or at most `1e-12`, R² is unavailable while
valid MAE/RMSE remain reportable. MAE-based source selection need not improve
RMSE or R²; a disagreement between losses is not justification for retuning.

## Conditional external uncertainty

Request exactly 128 paired external case-group bootstrap draws with replacement,
each of the same size as the gene's fixed complete external support. The
same drawn cases must score all four fixed predictors, the selected predictor,
and both paired deltas in a replicate. Seed deterministically from the frozen
protocol/request binding and gene; bind the seed context and record the seed.
No successful-only redraws or external outcome-dependent seed search are
allowed. Require at least 103 joint finite MAE/RMSE replicate evaluations for
nominal 90% intervals; retain attempted, successful and failed counts.

Use nearest-rank percentiles without interpolation: with `B` valid draws,
the lower order statistic is `max(1, ceil(0.05 * B))` and the upper is
`min(B, ceil(0.95 * B))`. R² intervals have their own finite-denominator support
and require 103 valid draws; unavailable R² must not suppress valid loss
intervals. Interval failure does not erase already computable point metrics;
report the uncertainty abstention explicitly.

These intervals condition on the fitted source data, final model choice,
frozen coefficients, provider processing, observed complete-case support and
case-group independence assumption. **Training uncertainty is unavailable in
this version:** training transforms are not refitted and selection is not
repeated. This is not a full nested training/bootstrap uncertainty analysis,
an empirically calibrated confidence procedure, or an individual prediction
interval. Shared TMT references, plex effects and possible donor relationships
can violate independent case sampling; this bootstrap does not model those
dependencies. A future full-training or cluster-aware uncertainty study needs
a new frozen protocol and cannot be claimed from this conditional interval.

## Required receipts and release checks

Before external scoring, freeze source and external plan/file hashes, exact
protein/channel-map/HGNC locks, processing-boundary receipt, panel, profile,
all support gates, complete model/solver/selector source dependencies, fold
rule, endpoint signs, seed derivation and runtime versions. Preserve the
original official processing captures privately; a printable boundary receipt
may reference their hashes without silently changing control characters or
other original metadata. Hash integrity is not issuer authentication or
independent re-proof of captured specimen joins.

Synthetic tests must verify source-only folds and transforms; outer held-out
label exclusion during inner selection; source final choice before external
scoring; exact tie order; strict all-five-family source coverage; unchanged
48/32/3/4-of-5/60 gates; the separate external 48-case gate; zeros, blanks and
structural absences; final-refit and convergence failures; paired external
draws; metric-specific R² availability; frozen training during uncertainty;
and hidden, immutable, nonpickleable transient predictors. Hand-derived
arithmetic oracles must check paired delta signs and common support. Tests are
software evidence, not biological validation.

The local report must expose each gene's source and external support,
selection evidence, numerical failures, all fixed-family and selected-policy
losses, conditional uncertainty scope, and structured abstentions. It must
keep `aligned_external_validation`, `clinical_validation` and default-model
promotion false. A successful stress computation does not admit clinical
eligibility, genetic donor independence or complete processing identity.

Persist only aggregate local receipts, source hashes and whole-order digests.
Do not export case/sample/aliquot/file identifiers, individual fold maps,
feature vectors, predictions, residuals or bootstrap indices. Source matrices,
private bindings and real-data derivatives remain
`local_only_terms_unverified`, outside Git and uploads. Require deterministic
replay into a fresh directory and independent aggregate/privacy review before
packaging. This document contains protocol metadata and no measured model
performance, coefficient, discovery count or claimed external result.
