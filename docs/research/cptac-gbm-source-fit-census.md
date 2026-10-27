# CPTAC GBM gene-wide source-fit census

Profile `cptac-gbm-source-fit-census/1.0.0`, evaluation
`cptac-gbm-real-gene-wide-source-fit-census/1.0.0`, attempts the unchanged
source reconstruction procedure for every identity on the previously defined
source feature axis. The driver is
`tools/evaluate_cptac_gbm_source_fit_census.py`. It records actual source-fit
acceptance and failures, then evaluates the frozen source predictors against
external provider coordinates. It does not select or rank genes.

This is a **post hoc descriptive computational census**. Earlier panel,
transfer and feature-coverage results were inspected during platform
development. Freeze this method, implementation, bounds, source bindings and
synthetic tests before the first real gene-wide census fit. That freeze does
not make the cohorts previously untouched or establish prospective biological
validation. This specification contains no census outcome or derived gene
count.

The [source-defined feature-space method](cptac-gbm-feature-space.md) supplies
the approved discovery-protein HGNC identities union all sixteen literature
anchors, in lexicographic HGNC-ID order. Preserve that complete axis, including
source-absent anchors, unresolved assay projections and count-capacity failures.
The source count-capacity flag and 26-context variation diagnostics remain
descriptive covariates. Neither filters which genes receive a source attempt.

## Fixed inputs and unchanged estimator

Use the existing exact-byte-locked discovery/confirmatory protein matrices and
channel maps, paired GDC STAR/AscatNGS files, approved HGNC snapshot and frozen
case/specimen/file plans. The plans contain 72 source and 56 external case
groups; these are fixed input inventories, not new clinical cohort claims.
Hashes bind local integrity and asserted provenance, not issuer authenticity,
donor independence or redistribution permission.

Preserve the original source case order and deterministic five patient folds:
sort SHA256 of exact source case-key UTF-8 bytes, break digest ties by case key,
and assign round-robin modulo five. Extract one identity's aligned CNV, RNA and
protein values without reordering patients or changing missingness. An aligned
single-pass adapter may avoid repeated identity searches; it must supply the
same vectors as the existing per-gene adapter.

Keep CDAP unshared median-normalized log2 specimen/reference protein ratios,
STAR unstranded FPKM-UQ and AscatNGS integer total copy number. Do not impute,
convert CNV to GISTIC, substitute all-peptide ratios, add `log1p`, renormalize
against external measurements or correct batches. Finite zeros remain
observations; structurally absent features and blank cells remain unavailable.
[PDC quantitation documentation](https://pdc-docs.cancer.gov/pdc/explore-quantitation-data),
[GDC RNA pipeline](https://docs.gdc.cancer.gov/Data/Bioinformatics_Pipelines/Expression_mRNA_Pipeline/),
[GDC CNV pipeline](https://docs.gdc.cancer.gov/Data/Bioinformatics_Pipelines/CNV_Pipeline/)

Invoke the existing `transfer.fit_source_gene` without changing its equations,
thresholds, numerical budget or return contracts. Preserve its four families
in order: `training_median`, `rna_only`, `cnv_only`, `full`. Their training-only
transforms, adaptive-MAD Huber fits, 240-iteration cap and existing numerical
failure rules are unchanged. Constant coordinates are not silently removed,
and a failed full family is not replaced by a reduced model.

The inherited source procedure retains:

| Operation | Existing requirement |
| --- | --- |
| Outer fitting | At least 48 training and 3 held-out joint-complete cases; at least four accepted outer comparisons and 60 common OOF observations. |
| Inner family selection | Four remaining folds, training minimum 32 and validation minimum 3; complete pooled inner OOF MAE, with explicit training-median fallback when support or candidate availability fails. |
| Final source family selection | All four fixed candidates have finite OOF predictions for every source joint-complete case across the original five folds; choose the lowest unrounded pooled OOF MAE. |
| Exact ties | Median, then RNA-only, then CNV-only, then full. |
| Full-source refitting | All four fixed families must return available full-source predictors. |

These are the existing fitter's operational acceptance rules. Acceptance does
not independently establish design rank, conditional-effect identification,
population representativeness, statistical power or biological validity.

## Full-axis source attempts and failure accounting

Every retained HGNC identity receives a source-attempt record in axis order.
Keep full original `SourceFitReceipt` fields whenever the unchanged fitter
returns one: profile ID, acceptance, complete and OOF counts, valid folds,
selected family, final-selection evidence, nested point summary, complete
fold traces, iteration diagnostics, final-fit evidence and failure reason.
Do not relabel the child legacy profile or reduce its evidence to a single
acceptance boolean. The new census profile belongs to the enclosing record
and manifests.

The existing fitter accepts finite input magnitudes at most `1e12`, apart
from allowed missing values. Retain an expected out-of-domain rejection as
its own explicit stage and reason; never clip, rescale or drop that identity.
An input-domain exception does not create a legacy fit receipt or predictor.
Its source field is `None` and its rejection is the literal
`source finite inputs exceed the frozen fitting magnitude domain`. Every
identity remains represented in later stage accounting, including external
coverage and an external-not-attempted record when no real source fit exists.

Exceptions on otherwise valid inputs are not automatically scientific
abstentions. Abort an incomplete run on unexpected software errors, preserve
the completed diagnostic pages, and withhold the source-complete seal and
external reads. Do not fabricate missing receipts to make the census complete.
Retain inherited reasons verbatim: some combine support, numerical and
null-variation failures and cannot identify one causal failure mechanism.

Report the axis denominator, attempted identities, expected domain rejections,
returned source fits, accepted/abstained fits and the count-capacity/actual-fit
cross-tabulation. Their denominators differ. No source count flag or accepted
fraction is a measure of biological signal or clinical usefulness.

## Bounded source phase and private predictor continuity

Use deterministic contiguous pages in the fixed source identity order:

```text
default genes per page = 32
maximum genes per page = 64
maximum canonical page bytes = 8 MiB
maximum total source-phase bytes = 512 MiB
```

Each completed page preserves full gene records and original receipts and is
bound by its canonical digest. The source manifest binds ordered pages, their
byte lengths, record counts, feature-axis/catalog and protocol digests, and
complete attempt/status counts. Enforce limits before writing an oversized
page or sealing a source phase. Exceeding a bound produces an incomplete run,
not a data-dependent subset of the genes or a relaxed limit. Reject overwrites.

Finish all source attempts, persist every source page and seal the complete
source manifest **before any external measurement values are read**. The
manifest is aggregate evidence; it contains no fitted coefficients or patient
arrays. Typed gene records are legitimate structural sequences, including a
page whose record count happens to equal a cohort size; that fact never
permits arbitrary numeric patient vectors.

Retain private frozen predictors only in RAM. Reconstructing a scoring view
from the sealed receipt pages must bind those receipts to the same private
predictors already produced in this process, with no fitting call or family
reselection. Do not serialize, pickle or cache predictors, patient values,
predictions or residuals. A crash loses the private predictors and requires
source replay under the same protocol before external scoring can resume.
Receipt-only hydration cannot recreate a predictor from aggregate evidence.

## External scoring and fixed-panel replay

After the complete source seal, project the external cohort onto the unchanged
source axis. Additional external protein identities do not expand that axis.
Each identity receives an external-stage record. Pass every real returned
source fit, including an unaccepted fit, to the unchanged
`transfer.evaluate_external_gene`; preserve expected domain rejections and
unavailable-source stages explicitly. Do not adapt a source model to external
coverage, correlations, errors or numerical failures.

The legacy evaluator uses the same external joint-complete patients for all
four fixed families and the source-selected policy, with a minimum of 48.
No model-specific observation deletion is allowed. Preserve MAE, RMSE and R2
relative to the frozen **source-training median**, not the external mean.
Negative R2 is valid. An undefined source-median null denominator leaves R2
unavailable without replacing valid MAE/RMSE by a biological interpretation.
Primary is `MAE(full) - MAE(CNV-only)`; secondary is
`MAE(selected) - MAE(full)`. Preserve both signs and negative outcomes.

The sixteen literature anchors use the exact historical provider-transfer
request digest:

```text
SHA256(canonical JSON {
  "protocol_digest": "sha256:94b76dada0f8c48aab989500b58e85462f30791508bac161e7216305c6bec588",
  "gene": exact historical approved anchor symbol
})
```

Represent the result as lowercase `sha256:`-namespaced hexadecimal, as in the
historical canonical digest helper; a bare hexadecimal token is not equivalent.

Nonanchors use a separately protocol-bound request derived from the new census
protocol digest and stable HGNC ID, with exact canonical keys
`{"census_protocol_digest": NEW_PROTOCOL_DIGEST, "hgnc_id": identity.hgnc_id}`.
The anchor exception preserves their complete old source receipts
and external `TransferGeneResult`, including request, seeds, intervals,
abstentions and child profile IDs. Require exact aggregate equality against
the historical results; a count-only or point-only match is insufficient.
Gene-wise request domains do not imply a shared cross-gene bootstrap schedule.

The unchanged evaluator makes 128 paired **external-patient** bootstrap
attempts per scoreable gene and requires 103 successful draws. It does not
perform 128 source refits or repeat source selection. The same resampled
external patients supply every model within a gene. Preserve its nominal 90%
nearest-rank percentile intervals and separately available R2 intervals;
these are conditional on the original frozen source predictors and selections.
No calibrated or simultaneous coverage is established by this census.

Keep four statuses distinct: source acceptance, external support, finite
external point-score availability and conditional-interval acceptance. The
legacy result can retain finite point metrics while its final acceptance is
false because the bootstrap support requirement failed. Preserve that result
and its reason rather than erase the point metrics or promote the gene.
In addition to source acceptance, count external support, point availability
and interval availability as three separate external-stage counters; retain
the evaluator's final acceptance separately. An external finite input over
`1e12` produces the explicit
`external finite inputs exceed the frozen scoring magnitude domain` rejection.
Its coverage remains visible; no clipping, observation deletion or invented
legacy result is allowed. Unexpected errors on valid inputs stop the incomplete
run.

External result pages retain the same 64-gene and 8 MiB per-page bounds.
Their cumulative phase cap is 512 MiB **including the external manifest**.
Preflight cumulative page bytes before opening a new output file, then verify
the full page-plus-manifest total before sealing. Re-read declared page bytes
with a size-plus-one cap and compare opened-descriptor and path snapshots;
reject changed, oversized, replaced or nonregular files. A size check alone
does not establish that the bytes verified are the bytes originally sealed.

## Interpretation, privacy and release controls

The nested point summary assesses the inherited inner-selection policy on
held-out source folds. The minimum final-selection OOF MAE is a criterion used
to choose the final family, not an unbiased error estimate of that selected
winner. Selecting or ranking genes using the same outcome summaries would
require a new selection/assessment protocol, not a reinterpretation of this
census. These primary methodological studies illustrate selection bias; they
do not prove coverage for this exact glioma procedure.
[Ambroise and McLachlan](https://pubmed.ncbi.nlm.nih.gov/11983868/),
[Varma and Simon](https://pubmed.ncbi.nlm.nih.gov/16504092/)

Across genes, common-case supports and protein variation differ. Gene-case
observations are not independent biological patients. Do not turn point signs,
nominal interval exclusions or selected-family frequencies into significance,
FDR-controlled discoveries, equivalence claims or a winner-ranked gene list.
Equal policy/full scores can arise from the identical selected predictor;
that equality does not establish equivalence between scientific hypotheses.

The parent CPTAC resource supports multimodal GBM research; successful
reconstruction is not a new glioma mechanism or target. Relative reference
coordinates, historical processing, tissue composition, missingness and cohort
differences can influence transport errors. Physical reference equivalence,
complete processing identity, genetic donor independence and contemporary
molecular/clinical eligibility remain unproved.
[Wang et al. primary study](https://pmc.ncbi.nlm.nih.gov/articles/PMC8044053/)

Outputs contain approved gene identities, aggregate evidence, bounded failure
diagnostics and integrity digests. They contain no patient/specimen/file IDs,
measurement vectors, fitted coefficients, predictions, residuals or patient
fold memberships. Source-derived pages, manifests and results remain
`local_only_terms_unverified` and are not committed or uploaded. No causal,
clinical, novel-biomarker, aligned-biological-validation or AlphaFold-scale
claim follows, and no model is promoted as a default.

Release requires synthetic full-axis/no-filter and stage-conservation tests;
source-before-external and no-refit hydration controls; exact paging/boundary,
digest, privacy and no-overwrite checks; independent numerical/comparison
oracles; and complete old-anchor replay. Freeze the method before real census
fitting, complete two deterministic local runs, verify aggregate repeat
identity, and independently review raw-source parity, numerical scope and
privacy. Actual counts, coefficients and outcome files remain local.
