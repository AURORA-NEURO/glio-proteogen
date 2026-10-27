# CPTAC GBM real-data conditional-association evaluation

The `cptac-gbm-real-data-evaluation/2.0.0` protocol deepens the existing local
`cptac-gbm-transcript-protein-discordance/1.0.0` feature using real, exact-source
CPTAC CNV, RNA, and protein measurements. It evaluates a fixed literature-based
glioma panel, retains unavailable/abstained genes, checks aggregate numerical
agreement, and exposes missingness, identifiability, and held-out fit
diagnostics. Version 2 adds an explicitly versioned, bounded 240-iteration
continuation candidate alongside the unchanged 30-iteration legacy estimator.
It does not use the synthetic cohort-replication demo as evidence.

Numerical results belong to the generated local evaluation receipt. A completed
run establishes computation on the admitted source bytes and internal
source-cohort evaluation, not external validation, a new disease classifier,
mechanistic discovery, patient-level prediction, or clinical utility. The
upstream preprocessing and panel-selection limitations below apply even when
every software and replay check passes.

## Frozen panel and rationale

The following sixteen exact HGNC symbols were fixed before running the local
fits for this evaluation:

```text
EGFR PDGFRA NF1 PTEN PIK3CA PIK3R1 PTPN11 PLCG1
TP53 MDM2 MDM4
RB1 CDK4 CDKN2A CDKN2B
IDH1
```

The first group covers receptor/PI3K-associated context; the second p53-related
context; the third RB/cell-cycle context; and the last IDH-related context.
These are literature-motivated panel groupings, not fitted pathway activities
or statistically independent hypothesis families. Wang et al. highlight
PTPN11/PLCG1 phosphosite observations and EGFR-, TP53-, and RB1-altered tumors
in their [CPTAC primary study](https://pmc.ncbi.nlm.nih.gov/articles/PMC8044053/).
The [Brennan et al. TCGA GBM primary analysis](https://pmc.ncbi.nlm.nih.gov/articles/PMC3910500/),
DOI `10.1016/j.cell.2013.09.034`, provides genomic context for RTK/PI3K,
p53/RB, and IDH-related genes. This
evaluation uses total gene-level protein abundance; it does not reproduce
phosphosite activation findings from the literature.

The panel is prespecified for this software run, not prospectively selected
before the source study or independent of all knowledge of its outcomes.
Published findings from the same cohort informed its scientific motivation.
Its results therefore cannot be advertised as independent confirmation of
those findings or as an unbiased genome-wide discovery experiment. Missing or
unstable genes must not be replaced after inspection, and the declared panel
must remain visible in the evaluation manifest. IDH1 protein abundance never
establishes IDH mutation status.

## Exact sources and disease boundary

| Input | Exact bytes | SHA-256 |
| --- | ---: | --- |
| Wang et al. Table S2, `NIHMS1665743-supplement-3.xlsx` | 129,239,538 | `59c33b6140c88c394da50fd7461774233074dda12361df7989fe51b8b8e28a13` |
| Frozen HGNC complete set, `hgnc_complete_set.txt` | 16,948,224 | `854162118530e929f06249f3349465dd5fe0515fcccf0347f463e833609c1270` |

The official [Table S2 download](https://pmc.ncbi.nlm.nih.gov/articles/instance/8044053/bin/NIHMS1665743-supplement-3.xlsx)
contains the source measurements. The HGNC source is the
[official complete-set export](https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/hgnc_complete_set.txt);
the current file at that URL can change and is not interchangeable with the
locked snapshot. Both local inputs were checked against these byte counts and
digests before the evaluation. The fitting path additionally hashes while
copying each input to a private temporary snapshot and parses those exact
snapshots.

The existing parser resolves 96 common measurement columns into 96 patient
groups and 10,430 common mapped genes. The publication's 99 treatment-naive
tumors and this 96-group multi-assay intersection describe different
populations. They must not be reported interchangeably. Normal brain source
columns are not extra independent training patients in this fitted cohort.

The source uses historical GBM terminology and includes molecular contexts
that cannot be silently equated with a pure WHO CNS5 IDH-wildtype glioblastoma
cohort. This evaluation does not apply a newly verified molecular-class filter
or infer a class from the panel's expression. Its scope is the locked historical
CPTAC GBM cohort. An IDH-wildtype-only analysis would require an admitted
patient-level molecular-status crosswalk, a new declared subset/protocol, and
appropriate sample-size and split checks. See the
[WHO CNS5 author summary](https://pmc.ncbi.nlm.nih.gov/articles/PMC8328013/).

## Estimand and locked fitting procedure

The question is whether RNA adds held-out information for the source's
protein-abundance axis after including the same gene's CNV. For each eligible
gene, the existing fitter evaluates:

```text
full:      Protein ~ intercept + RNA + CNV
RNA-only:  Protein ~ intercept + RNA
CNV-only:  Protein ~ intercept + CNV
baseline:  training-fold median Protein
```

The primary incremental metric is held-out full-model R² minus held-out
CNV-only R² on their common accepted support. Incremental R² versus RNA-only
is a separate comparator. Negative R² and negative incremental R² are valid
outcomes and must be preserved. A full-model residual is an observational
prediction error, not unexplained biology. The conditional RNA coefficient is
reported on the source axes; RNA and protein are not subtracted.

The locked numerical fit uses five deterministic outcome-blind patient folds.
Only jointly finite CNV/RNA/protein rows enter a fold's fitting/evaluation
support; missing values are not imputed as measurements. Within training
folds, the robust fitter estimates median centers, `1.4826 * MAD` scales with
an SD fallback, and Huber IRLS coefficients (`k=1.345`, at most 30 iterations,
`1e-8` convergence tolerance, `1e-8` slope ridge). A contributing fold requires
at least 48 complete training groups, three complete held-out groups, and
identified/converged model families. A gene needs at least four valid folds
and 60 aggregate out-of-fold observations.

The existing 128 deterministic fold-stratified patient-bootstrap refits
estimate nominal 90% nearest-rank intervals. At least 103 complete refits must
succeed. They describe source-cohort sampling variability; they are not
calibrated patient-prediction or external-validation intervals. Runtime pattern
rules retain their existing `limited` ceiling and 0.80 fold-sign-stability
criterion. An interval crossing a prespecified zero boundary is not a new
significance test. This evaluation does not modify that v1 fitting profile.

See the [existing lane specification](cptac-gbm-transcript-protein-discordance.md)
for its artifact, query, interval, and pattern semantics. Table S3 reported-call
flags are not fitting inputs, labels, or eligibility filters here; their zero
or absence cannot be interpreted as a tested biological negative.

## Version 2 numerical continuation candidate

An initial real-source evaluation exposed failures in well-conditioned
training designs where one or more adaptive-MAD Huber fits reached the
30-iteration cap. Other genes lacked enough complete measurements to enter a
valid training fold. These are different failure mechanisms. A bounded
numerical continuation can address an iteration-budget failure; it cannot
create missing measurements or repair unsupported inference.

The continuation candidate lives within this existing research feature in
[`continuation.py`](../../src/glio_proteogen/research/cptac_gbm_transcript_protein_discordance/continuation.py),
with profile ID `cptac-gbm-transcript-protein-continuation/1.0.0`. It is a
separately versioned numerical policy, with its own source/policy binding,
rather than an unrecorded change to legacy 1.0. The
ordinary legacy artifact, profile, fitting limits, query, and exact replay
remain unchanged. Candidate results are local development/evaluation
aggregates and must not be loaded into the legacy artifact format as though
the old estimator produced them.

The candidate permits up to 240 total IRLS iterations while preserving the
existing training transforms, adaptive residual-MAD scale update, Huber
constant, ridge, `1e-8` convergence tolerance, and deterministic ordering.
The minimum 48 training/three held-out complete cases, four accepted folds,
60 common OOF observations, and 103 of 128 successful bootstrap refits are not
lowered. Missing and unsupported evidence remain explicit. Already converged
fits must agree with the legacy calculation; exhausted or otherwise failed
fits remain distinguishable from converged fits.

This is a numerical fidelity change, not a new biological estimand. A recovered
fit means the same iterative calculation met its numerical and evidence
conditions with a longer bounded budget. It does not establish stronger
association, a new discovery, better interval calibration, or external
validity. The adaptive-MAD loop is a fixed-point iteration; convergence is not
proof that a single fixed convex objective decreased at every step or that a
global optimum has been established. The candidate emits no new biological
pattern label.

The numerical policy was motivated by failures observed in this development
cohort. That cohort consequently cannot serve as blinded, independent evidence
that the chosen budget is optimal or generally sufficient. Evaluate the full
unchanged panel under both policies, retain the initial failures, and expose
all budget-limited, numerical, missingness, and uncertainty abstentions.

### Paired point-fit and uncertainty comparisons

The runner calls `evaluate_convergence_budgets(cnv, rna, protein, folds)` from
[`convergence_audit.py`](../../src/glio_proteogen/research/cptac_gbm_transcript_protein_discordance/convergence_audit.py)
for the fixed budgets `(30, 60, 120, 240)`. It evaluates the full, RNA-only,
CNV-only, and training-median models on one intersection of folds accepted by
all four budgets. `common_accepted_folds` and `common_oof_count` define that
shared support; every budget's four reconstruction summaries use exactly that
intersection. At least four common folds and 60 common OOF observations are
required for `comparison_status=matched_support_sufficient`. Smaller
intersections remain `descriptive_insufficient_common_support`, even when a
higher budget recovers enough observations for its own candidate point fit.
This audit emits no bootstrap evidence or artifact promotion.

Report matched-support performance separately from newly recovered OOF
coverage. A metric computed on additional held-out observations
cannot be compared to an old metric on a smaller set as though only the
coefficients changed. Newly recovered coverage is useful but is a separate
endpoint from improved error on matched observations.

The 128-refit numerical comparison uses the original legacy profile, exact
source locks, and gene-specific fitting seed as its common draw basis. Its
binding and seed must be recorded in the protocol/receipt. Changing the
candidate source digest must not silently change bootstrap draws between
budgets and confound numerical recovery with Monte Carlo variation. Within
each replicate, resample the same patient groups within their original fold
strata and refit all training transforms and models under each policy. A
failed draw is counted as failed; it is not redrawn until it succeeds.

Nominal 90% candidate intervals come from the accepted continued refits and
retain the existing support gate. When the two policies accept different
replicate subsets, their interval summaries condition on different successful
samples even though the underlying draws are paired. Report success counts
and explicit paired-comparison support; do not describe a narrower interval
as a calibrated uncertainty improvement. No patient arrays, row identities,
OOF vectors, or bootstrap resample indices are persisted.

### Local library API and receipt meaning

The library entry point is:

```text
fit_continuation_gene(cnv, rna, protein, folds, *, request_digest, budget=240)
```

It accepts aligned transient NumPy arrays under the existing validation
semantics and rejects a public budget other than the exact Python integer
240. The original gene-specific fitting digest is the `request_digest` for
this numerical comparison. The returned `ContinuationGeneResult` binds
`profile_id`, `profile_digest`, `budget`, `comparison_request_digest`,
`comparison_bootstrap_seed`, and `comparison_seed_context`. Its profile digest
binds the continuation, budget-audit, and budget-solver source files plus the
legacy semantic dependency. No global legacy solver setting is changed.

The result exposes `accepted`, `point_valid_folds`,
`point_oof_patient_groups`, aggregate `point_folds`, `bootstrap_requested`,
`bootstrap_attempted`, `bootstrap_successful`, `bootstrap_required`,
`summary`, `failure_reason`, and limitations. A point-stage abstention can
have 128 requested but zero attempted bootstrap refits; do not call it
bootstrap instability. An accepted result contains an aggregate summary with
the same metric and nominal interval definitions as the existing feature.
`accepted` denotes completion of numerical/point-support/bootstrap gates, not
predictive quality or conditional biological identification. Review the
separate input-design diagnostics, comparator errors, and coverage before any
interpretation. No new biological label is assigned.

This continuation API is local library functionality and part of the local
evaluation runner. It does not add an HTTP inference endpoint or replace the
existing feature's CLI query/replay semantics.

## Preprocessing boundary: internal evaluation is not end-to-end validation

The source README describes protein measurements as already log2 transformed,
median-polish normalized, and ComBat batch corrected. RNA is FPKM-UQ and CNV
is a GISTIC2.0 gene-level axis. Those whole-cohort source processing steps were
completed before the local train/test split. The local fitter does not recover
or refit the original normalization and ComBat procedure within every fold.

Consequently, the regression centers, scales, coefficients, and bootstrap
refits can be fold-local while the supplied matrix still carries a
whole-cohort, potentially transductive preprocessing boundary. Held-out
measurements may already have influenced source normalization or batch
parameters. The evaluation must be described as internal regression evaluation
conditional on the published processed matrix, not a fully leakage-free
end-to-end estimate for new patients, laboratories, or source cohorts. The
size and direction of any effect of this boundary have not been established
by this run.

The molecular-class mixture, complete-case selection, upstream missingness
filtering, and absence of age/sex/purity/mutation covariates further limit
interpretation. All are reasons to qualify the estimand, rather than silently
correct source values or declare missing biology absent. This is not an
iProFun reproduction or causal mediation analysis.

## Additive input and evaluation diagnostics

The additive diagnostics operate on transient, exact-source arrays and emit
only bounded feature/fold aggregates. They do not change existing point fits,
bootstrap intervals, gene-pattern rules, or artifact support. Every panel
member retains a record even when it is absent from the common feature axis,
fails support, or is not numerically estimable.
The evaluator's `conditional_effect_reportable` requires all three gates: an
accepted legacy 128-bootstrap fit, exact agreement of independently
recomputed point OOF values/support with that fit, and numerical identification
of all eligible training designs. The runner exposes this as
`conditional_direction_eligible`. A legacy pattern stored for replay remains
a legacy output; it must not override a failed diagnostic gate on interpreting
a conditional direction.

For each mapped gene, retain the eight joint observed/missing patterns across
CNV, RNA, and protein. Summarize counts rather than source rows or participant
identifiers. For each fold, report complete training and test counts and the
existing point-fit support/convergence failure reason. A request-wide gene
mapping failure must not silently become a different panel: the numerical
fitter may consume the mapped eligible subset only if the evaluation record
retains the original sixteen-symbol declaration and explicit unavailable
members.

The collinearity diagnostics examine the training mean-centered,
sample-SD-standardized design `[intercept, RNA, CNV]`: design rank, condition
number, CNV--RNA Pearson correlation, and the fraction of standardized RNA
variance remaining after its ordinary linear projection on intercept/CNV.
This diagnostic scaling does not replace the robust fitter's median/MAD
scaling. SVD rank counts singular values above
`float64_epsilon * max(design.shape) * largest_singular_value`.
The RNA fraction is the squared OLS residual norm divided by the standardized
RNA squared norm, bounded to [0, 1]; it is not computed by subtracting a
rounded correlation squared from one. A diagnostic
flag is raised when rank is below three, the condition number exceeds `1e6`,
or the residual-RNA variance fraction is below `1e-6`. Constants and
insufficient training support receive explicit reasons. These are numerical
review thresholds, not calibrated biological or clinical decision rules.
The aggregate conditional-identification gate examines folds with at least
48 complete training groups; no eligible design, or any unidentified eligible
design, withholds conditional interpretation. A rank-deficient design has no
finite condition number reported, rather than a fabricated finite value.
The aggregate flag `conditional_design_unidentified` can therefore mean no
training fold had enough complete cases to be eligible, even when the smaller
designs that were inspected have full rank. Inspect the coverage counts and
fold-specific reasons before calling such a case collinear. MDM2, MDM4, and
CDKN2B illustrate the distinction in the initial source audit; extending IRLS
does not remove their complete-case support requirement.

Strong RNA--CNV dependence can make their conditional coefficients unstable,
weakly identified, or sensitive to small errors even when the combined model
predicts reasonably. A ridge-stabilized estimate is not evidence that the
underlying biological contributions are separately identified. Conversely,
well-conditioned input does not eliminate omitted confounding, nonlinearity,
measurement error, composition effects, or selection bias. A negative
conditional coefficient cannot establish repression or buffering.

On common supported out-of-fold observations, report the full, RNA-only,
CNV-only, and training-median models' R², MAE, and RMSE. Additional descriptive
checks include calibration intercept/slope and residual association with RNA
and CNV. The calibration line is fitted to pooled held-out predictions for
diagnosis only; it is not an independently validated recalibration model.
Diagnostic OOF metrics can exist even when fewer than the required folds or
bootstrap replicates pass; their presence does not create an accepted legacy
fit or a reportable conditional effect. A nonestimable R² denominator remains
null.
Residual correlations are diagnostics of the evaluated model/support, not
conditional causal effects, independent null tests, or proofs of model
adequacy. Repeated folds reuse the cohort; fold-level metrics are not five
independent studies.

The evaluation independently orchestrates point refits through the same shared
Huber solver and compares exact OOF predictions/support with the existing fit
where available. It is a numerical agreement audit, not an independent
implementation of the Huber estimator. Agreement and deterministic replay
verify numerical behavior and provenance binding. They do not turn a
whole-cohort source preprocessing step into an independent observation.

## No naive conditional p-values or invented standard errors

This run does not estimate a conditional permutation p-value, empirical false
discovery rate, or calibrated family-wide significance. Independently shuffling
RNA changes its dependence on CNV and can test a different null from “RNA
adds information after CNV.” A valid conditional-null extension would need a
prespecified nuisance/generative model or exchangeability assumption,
patient-aware randomization, full training-fold refitting, known-null checks,
and adequate Monte Carlo resolution. A global-shuffle negative control, if
reported separately, would be descriptive sensitivity rather than calibrated
conditional inference.

The fixed literature panel and nominal bootstrap intervals do not remove
selection, correlated-feature, and multiplicity concerns. Counts of
interval-supported patterns are descriptive outputs, not a count of validated
discoveries. The analysis must retain abstentions and negative comparator
results rather than optimize the panel after inspection.

The existing source-scale slope and asymmetric percentile intervals are not a
validated effect/SE input to the aggregate
[cohort-replication engine](cohort-replication.md). Do not relabel a raw slope as
a standardized coefficient, divide its interval width by a normal quantile to
invent an SE, or treat folds/bootstrap replicates as independent cohorts.

## Execution, local outputs, and terms

The additive real-data runner fixes its panel and protocol before parsing the
source matrices. Run it against exact local source copies and a new local
output directory. Version 2 evaluates the legacy and bounded continuation
candidate together by default:

```text
uv run python -m tools.evaluate_cptac_gbm_real_data --table-s2 <local-exact-Table-S2.xlsx> --hgnc <local-exact-hgnc_complete_set.txt> --output-dir <new-local-output-directory>
```

Its generated protocol binds the source locks, panel, legacy fitter profile,
continuation policy/source, common bootstrap draw basis, tool/diagnostics source
digests, environment, and interpretation policy. Per-gene JSON and the final
`evaluation.json`/`summary.csv` retain the declared panel, legacy and candidate
diagnostics, common-support comparisons, accepted/abstained/unavailable states,
and fitted metrics where eligible. If at least one legacy gene is fitted, the
runner also writes the unchanged ordinary v1 `artifact.json`, `request.json`,
`result.json`, `replay-envelope.json`, and `replay-verification.json`.
Continuation aggregates are separately identified in the evaluation receipt;
they are not relabeled legacy artifacts. These files remain local-only and are
not test fixtures or public scientific evidence merely because they are
reproducible.

The existing exact-source fitting command is:

```text
uv run glio-proteogen cptac-gbm-transcript-protein-discordance fit-local \
  --table-s2 <local-exact-Table-S2.xlsx> \
  --hgnc <local-exact-hgnc_complete_set.txt> \
  --output <new-local-artifact.json> \
  --gene EGFR --gene PDGFRA --gene NF1 --gene PTEN \
  --gene PIK3CA --gene PIK3R1 --gene PTPN11 --gene PLCG1 \
  --gene TP53 --gene MDM2 --gene MDM4 --gene RB1 \
  --gene CDK4 --gene CDKN2A --gene CDKN2B --gene IDH1
```

This is shell-neutral command notation; replace continuations according to the
local shell. The strict fitter rejects a gene absent from the common source
axis. The additive real-data evaluation runner preserves such a member in its
frozen-panel receipt rather than replacing it. Inspect its output manifest
together with the tool source and generated receipt.

Source workbooks, patient matrices, sample headers, participant or
participant-derived identifiers, fold assignments, bootstrap resample indices,
OOF vectors, and residual arrays must remain outside committed/runtime
artifacts. Staging temporarily copies whole sources into a private local
directory, with ordinary success/failure cleanup; a host/process crash can
leave private temporary residue. Fitted coefficients, aggregate diagnostics,
source/profile/tool/result digests, replay status, and runtime/resource
measurements belong in local outputs only while redistribution terms remain
unverified.

The source publication URL and the
[PDC study page](https://pdc.cancer.gov/pdc/study/PDC000204) establish scientific
provenance, not permission to redistribute the exact supplementary workbook or
all derivative artifacts. The existing fitter's
`local_only_terms_unverified` boundary is preserved; PDC's separate
[data-use guidelines](https://pdc.cancer.gov/pdc/data-use-guidelines) must not be
assumed to settle supplement-specific terms. No real-source artifact is added
to source control by this evaluation protocol. Public code/tests may exercise
the same numerical diagnostics with synthetic oracles, clearly separated from
local real-data results.
