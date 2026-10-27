# CPTAC GBM nested comparator selection

The `cptac-gbm-nested-comparator-selection/1.0.0` profile evaluates a
training-only choice among a protein training median, RNA-only regression,
CNV-only regression, and combined RNA/CNV regression. The local runner uses
`cptac-gbm-real-nested-selection-evaluation/1.0.0`. This is an additional
prediction-policy evaluation within the existing CPTAC feature. It does not
change the original conditional-association estimator, its artifacts, its
support gates, or the separately versioned numerical continuation candidate.

The question is whether choosing a simpler or combined predictor using only
each outer training set yields useful held-out protein reconstruction on this
source cohort. A numerically accepted combined model need not predict better
than a simpler model. Selection by inner mean absolute error (MAE) does not
guarantee lower outer MAE, better R², or recovery of a particular gene's
predictive performance. Higher losses than a comparator and negative R² must
remain visible.

The policy was designed after inspecting earlier model comparisons from this
same cohort. Freezing the protocol before this run prevents further in-run
changes; it does not erase this outcome-informed development history. The
outer predictions exclude each held-out fold during fitting and selection,
but they are still internal development-cohort evidence, with the upstream
preprocessing boundary described below. No independent validation or new
biological finding follows from completing this workflow.

## Sources, panel, and admission

Use the exact Table S2 and HGNC snapshots admitted by the
[real-data evaluation protocol](cptac-gbm-real-data-evaluation.md). The runner
requires both input paths, verifies byte counts and SHA-256 digests while
staging private immutable copies, and checks the existing parser's exact
96-patient-group, 96-common-measurement, 10,430-common-gene invariants. A file
with the same name or a newer HGNC download is not an equivalent input.

The unchanged sixteen-gene panel is:

```text
EGFR PDGFRA NF1 PTEN PIK3CA PIK3R1 PTPN11 PLCG1
TP53 MDM2 MDM4 RB1 CDK4 CDKN2A CDKN2B IDH1
```

The runner records all panel members, including unavailable or abstained
members; it does not replace genes after inspection. The literature rationale
comes from [Wang et al., 2021](https://pmc.ncbi.nlm.nih.gov/articles/PMC8044053/)
and [Brennan et al., 2013](https://pmc.ncbi.nlm.nih.gov/articles/PMC3910500/).
This panel was informed by published glioma biology, including the source
study. It is not an outcome-independent, genome-wide discovery experiment.

The disease scope is the locked historical CPTAC GBM source cohort, including
IDH-mutant contexts. It has not been newly admitted as a pure WHO CNS5
IDH-wildtype glioblastoma cohort. IDH1 abundance does not establish mutation
status. Omitted tumor composition, batch, treatment, and other covariates can
affect reconstruction and selection.

All inputs and real-data derivatives retain `local_only_terms_unverified`.
Keep source measurements, identifiers, fitted results, numerical outcome
tables, and receipts in private local work directories. Do not commit them,
upload them, or substitute them for redistributable test fixtures. Committed
tests use small synthetic numerical oracles to verify behavior; those fixtures
are not glioma evidence.

## Locked candidate families and numerical fit

For one gene, the four families are:

```text
training_median: Protein prediction = median(training Protein)
rna_only:        Protein ~ intercept + RNA
cnv_only:        Protein ~ intercept + CNV
full:            Protein ~ intercept + RNA + CNV
```

Every family uses the same jointly finite CNV/RNA/protein observations. The
median and single-predictor families do not gain extra rows when another assay
is missing. There is no imputation of missing measurements. Thus the estimand
is restricted to the source's joint complete-case population, whose selection
may itself be informative.

Regression candidates use the existing robust Huber fitting equations with
the explicitly bounded 240-iteration solver. Each fit estimates its median
centers and MAD-based scales, including the existing SD fallback, solely on
that fit's training rows. The response transform is also fitted on training
rows. Huber tuning, convergence tolerance, slope ridge, and the permitted
iteration budget are fixed; selection does not tune them. This profile does
not increase an iteration budget in response to a gene's held-out error.

An unidentified, nonconverged, or non-finite candidate is unavailable. This
is numerical eligibility for prediction, not evidence that a conditional
coefficient is biologically identifiable. The nested result emits neither
a pooled RNA coefficient nor a biological pattern label.

## Nested algorithm

The outer partition is the existing deterministic five-fold patient
partition. All observations from one patient remain in that patient's
original fold. For an outer fold `o`, only the other four original folds
can enter selection and outer training.

1. Restrict training and held-out rows to the common complete-case mask. An
   outer fold needs at least 48 complete training observations and three
   complete held-out observations. Otherwise record an outer-support
   abstention; do not turn missing outer support into a median success.
2. Within the outer training set, use each of its four original folds once
   as inner validation and the other three as inner training. Every inner
   block needs at least 32 complete training observations and three complete
   validation observations. These are a new, explicitly versioned inner
   support policy. The value 32 is an engineering/research policy choice, not
   a statistically validated sample-size threshold or a relaxation of the
   original estimator's outer training minimum of 48.
3. If any required inner block fails the support policy, use the outer
   training protein median and record `fallback_inner_support`. No inner-MAE
   winner is asserted. In particular, do not discard the unsupported inner
   block and select a candidate using an easier subset.
4. Otherwise fit each candidate separately in every inner training block and
   predict its corresponding inner validation block. A candidate is eligible
   only when it supplies finite predictions for every observation in all four
   required validation blocks. A candidate failure disqualifies the candidate;
   it never removes rows from another candidate's loss calculation.
5. For each eligible candidate, pool its absolute errors over individual inner
   held-out observations and calculate one MAE. This weights patients, rather
   than giving unequal-sized folds equal weight. Compare unrounded finite
   MAEs on exactly the same observations and source protein scale. Do not
   pool raw gene-wise MAEs across different genes to select a global policy.
6. Choose the smallest inner MAE. Exact numerical ties follow the declared
   order `training_median`, `rna_only`, `cnv_only`, `full`. There is no
   tolerance band, post hoc simplicity penalty, or one-standard-error rule.
   Under supported finite inputs the median is available; if no candidate
   has complete finite inner support, record a median fallback with its reason.
7. Refit the selected family using the complete outer training set, with new
   training-only transformations. If the selected outer refit cannot supply
   finite predictions, record `fallback_selected_refit` and use the outer
   training protein median. No outer protein outcomes may choose the family
   or decide a fallback. A selected median is either a genuine inner-MAE
   choice or an explicit fallback; the trace distinguishes them.
8. Independently fit all four fixed families on that same outer training set
   to define fair fixed-policy comparators. Main comparisons admit only outer
   folds where the selected policy and all four fixed families supply finite
   predictions. Report selected-only coverage separately; do not compare
   performance calculated on different observation sets.
9. Pool predictions only after all outer folds have completed. The main point
   evaluation needs at least four accepted outer folds, at least 60 common
   out-of-fold (OOF) observations, and finite, defined metrics. A non-finite
   error sum or median-baseline squared-error sum at most `1e-12` makes
   relative R² undefined and cannot be replaced by an invented finite score.

This nesting treats selection as part of fitting, as motivated by the primary
analyses of [Varma and Simon, 2006](https://doi.org/10.1186/1471-2105-7-91)
and [Cawley and Talbot, 2010](https://www.jmlr.org/papers/v11/cawley10a.html).
Those studies support separating selection from evaluation; they do not
establish calibration for this particular source, support rule, or bootstrap.

## Common-support metrics and direction

All five policies, selected plus the four fixed families, use one common
outer OOF mask for the main comparisons. Report MAE, root mean squared error
(RMSE), and the existing fold-training-median-relative R²:

```text
MAE(policy) = mean_i abs(Protein_i - Prediction_policy_i)
RMSE(policy) = sqrt(mean_i (Protein_i - Prediction_policy_i)^2)
R²(policy) = 1 - sum_i (Protein_i - Prediction_policy_i)^2
                / sum_i (Protein_i - Median_outer_train(i))^2
```

This R² uses each observation's outer-training median baseline. It is not
ordinary R² centered on the held-out outcomes' overall mean. The median
policy has relative R² zero when the common denominator is defined. Preserve
negative R² without clipping.

For each fixed comparator, paired deltas are:

```text
MAE difference = selected MAE - fixed-comparator MAE
R² difference = selected R² - fixed-comparator R²
```

A negative MAE difference favors selection; a positive R² difference favors
selection. These are prediction errors and comparative scores, not effect
sizes of a biological intervention. Inner selection optimizes MAE only, so a
favorable MAE comparison need not imply a favorable R² comparison. A claim
that one policy is useful must address the actual comparator scores and
coverage, rather than numerical acceptance alone.

Common-support exclusion is determined by fit availability and declared
rules, not by outer error ranking. It can still change the evaluated
population. The traces and selected-only coverage must therefore remain
visible, especially when a difficult fixed family prevents a main comparison.

## Full nested patient bootstrap

After a supported point fit, draw exactly 128 bootstrap samples using the
existing deterministic patient bootstrap stratified by original outer fold.
The comparison request digest is derived from the unchanged legacy profile,
exact source locks, and gene. It uses the same original request-digest PCG
draw basis as the previous continuation comparison. Record this basis and
the seed; a matching seed alone is insufficient if canonical ordering,
sampling strata, or draw order changes.

Every draw reruns the entire nested algorithm: complete-case masking, every
inner candidate fit and transformation, candidate eligibility, inner MAE,
selection and fallback, outer refits, all fixed comparators, common-support
construction, and metric calculation. Bootstrapping predictions from a
previously selected fixed winner does not implement this protocol.

Patient multiplicities act as bootstrap weights. Every copy of a sampled
patient stays in its original fold, including its inner validation stratum;
copies cannot appear on both sides of an outer or inner split. The support
counts inside a bootstrap draw count sampled observations with multiplicity;
they do not claim that duplicate draws create new independent patients. Draw
order is preserved after the initial canonical ordering.

Each successful draw must pass the unchanged main outer 48/3/4/60 and finite
metric gates. Its selected and fixed scores use that draw's one common mask.
This mask can vary across draws, which is part of the observed sampling and
availability sensitivity. Failed draws are counted and never replaced.
At least 103 of the 128 draws must succeed. If the point fit fails, bootstrap
attempts are zero; a requested count of 128 is not an attempted count.

The resulting nominal 90% nearest-rank percentile intervals summarize the
selected policy's MAE and relative R² and the paired differences versus each
fixed comparator. For `B` successful draws, endpoints use sorted ranks
`max(1, ceil(0.05 * B))` and `min(B, ceil(0.95 * B))`, without interpolation,
and the existing interval output quantization. They include reselection
variability within this procedure.
They are not calibrated postselection confidence statements, patient-level
prediction intervals, simultaneous intervals, clinical validation, or evidence
of a novel glioma mechanism. No empirical null calibration or interval-coverage
study is supplied here.

Point and accepted-bootstrap selection counts state both the number of
comparison-support fold decisions and the number of compared observations
assigned to each family. Their denominators differ and are explicit. These
frequencies describe algorithm instability conditional on accepted support;
they are not posterior biological probabilities or extra independent patient
observations. Selected families can differ across folds and draws, so no
single pooled conditional RNA slope is defined by this policy.

## Multiplicity and preprocessing boundaries

The sixteen genes, four candidate families, several comparators, and several
metrics do not constitute one unselected hypothesis test. Inner selection is
accounted for operationally by the outer loop and full bootstrap reselection.
That does not supply false discovery rate control, family-wise coverage, or
a p-value for the winning family. The protocol emits no conditional naive
p-values and no discovery calls. Retain all declared genes and comparators;
do not promote only favorable genes or revise the policy after seeing outer
scores without a new protocol and a fresh evaluation boundary.

The admitted workbook already contains whole-cohort normalization and ComBat
processing performed before these nested splits. Fitting and selection here
respect their local training boundaries, but upstream processed values can
share information across those boundaries. Thus this is not an end-to-end
leakage-free estimate from raw assays. Repeated review of this cohort also
makes it a development set. Neither issue is fixed by adding a second CV loop.

## Local operation and output contract

Run from the repository root with admitted source paths and a new output
directory outside the repository:

```powershell
uv run python -m tools.evaluate_cptac_gbm_nested_selection `
  --table-s2 <exact-Table-S2.xlsx> `
  --hgnc <exact-hgnc-complete-set.txt> `
  --output-dir <new-private-local-directory>
```

The runner freezes `protocol.json` before reading source measurements and
creates the output directory exclusively. It writes each `gene-<SYMBOL>.json`,
an aggregate `evaluation.json`, and `summary.csv`. Its canonical protocol
binds source locks, fixed panel, support rules, exact tie order, solver budget,
bootstrap policy, legacy profile, numerical source files, runner digest, and
runtime versions. The report binds the protocol digest and records abstentions
and limitations. Completion/status receipts are aggregate; transient patient
predictions and identifiers are not serialized.

The public computational entry point is
`fit_nested_selection_gene(cnv, rna, protein, folds, *, request_digest=...)`
in the existing research package's `nested_selection.py` module. Its
`NestedSelectionGeneResult` includes profile/request digests, point common and
selected-only OOF counts, fold traces, candidate eligibility and MAEs, point
comparative metrics, bootstrap requested/attempted/successful counts, nominal
uncertainty when accepted, explicit failure reason, and limitations.
`nested_selection_profile_digest()` binds the separate profile and its legacy
semantic dependencies. `nested_point_fit(...)` is a development-only transient
helper with nonserializable immutable arrays, not a patient-output API.

This workflow creates no original-profile artifact and adds no HTTP route.
Its numerical summary must not be relabeled as the original conditional
association result, a new trained clinical model, or external validation.

## Verification and next evidence boundary

Executable traceability is maintained in
[`cptac-gbm-nested-selection.csv`](../traceability/cptac-gbm-nested-selection.csv).
Required checks cover outcome isolation, training-only transforms, candidate
coverage, pooled-loss arithmetic, exact ties, explicit fallbacks, paired common
support, resampled patient grouping, full reselection, failed-draw accounting,
source admission, output privacy, and preservation of existing profiles.

An external follow-up must admit matched CNV, RNA, and protein with an audited
patient/sample crosswalk, molecular disease scope, treatment/timepoint scope,
gene mapping, compatible source axes, missingness, and reuse terms. Freeze the
policy and preprocessing before examining its outcomes. Separate a frozen
transport test from fitting this policy anew within another cohort.

Two concrete candidates are available for source-admission work, not yet
accepted validation evidence:

- [Kim et al., 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC10939876/)
  reports 123 longitudinal GBM pairs with WES, transcriptomics, and proteomics
  measured on different subsets. Its deposited accessions include
  [SRA PRJNA1051047](https://www.ncbi.nlm.nih.gov/bioproject/PRJNA1051047),
  [PDC000514](https://pdc.cancer.gov/pdc/study/PDC000514), and
  [PDC000515](https://pdc.cancer.gov/pdc/study/PDC000515). Existing local
  protein/phosphoprotein source locks do not establish an available, aligned
  CNV/RNA/protein validation intersection. Processed transcript abundance and
  its specimen crosswalk still require admission; raw-read availability alone
  does not supply an analysis-ready matrix. Primary and recurrent samples from
  a patient must remain grouped, and the phosphoproteomic subset is not an
  independent replication cohort.
- [Liu et al., 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11337243/)
  reports an expanded high-grade glioma cohort and provides data through
  [PDC000446](https://pdc.cancer.gov/pdc/study/PDC000446) and
  [GDC CPTAC-3](https://portal.gdc.cancer.gov/projects/CPTAC-3). Its publication
  preprocessing includes cross-cohort ComBat alignment and imputation.
  A jointly adjusted publication matrix is therefore not automatically an
  untouched external test, even if participant labels do not overlap. Prefer
  admitted non-imputed assay outputs with an independently specified
  preprocessing boundary. Official identifiers, study-version UUIDs, source
  hashes, donor overlap, specimen types, and case-level assay intersections
  still require an explicit audit. A separate publication or study accession
  alone never proves independence.

These candidate-source checks establish tractable next inputs. They do not
assert external predictive benefit, conditional-effect replication, assay
equivalence, or permission to redistribute human source data.
