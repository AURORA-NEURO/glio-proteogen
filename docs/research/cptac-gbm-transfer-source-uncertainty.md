# CPTAC GBM two-cohort source-uncertainty sensitivity

`cptac-gbm-provider-transfer-two-cohort-sensitivity/1.0.0` is an additive,
**post hoc empirical-bootstrap sensitivity analysis** of the frozen
[provider-transfer stress experiment](cptac-gbm-provider-transfer.md). Its
design follows inspection of that experiment's external results. It must not
be called a new prospective test, an independent confirmation, a calibrated
post-selection confidence procedure, or aligned biological validation.

The question is how the reported loss comparisons vary when both empirical
cohorts are perturbed and the source fitting/selection procedure is repeated.
The original profile, point estimates, support gates, panel, candidate order,
240-iteration solver and output files remain unchanged. Freeze this separate
method and its source bindings before examining any new resampling outcomes.
Do not change the loss, interval policy, seeds, support semantics or iteration
budget in response to those outcomes.

## What is resampled and what remains conditional

Retain the exact admitted 72-case source and 56-case external inventories,
their private specimen/file bindings, source locks, HGNC identities and
three assay coordinates. RNA, CNV and protein from one case remain paired.
Copies of a case carry the same original measurements and missingness; there
is no independent resampling of assays, imputation or synthetic patient.
The sixteen-gene panel and all original point-stage abstentions remain visible.
Only genes eligible under the original unresampled source/external policy
enter refit sensitivity. A bootstrap draw cannot rescue a point-ineligible
gene or replace it with another gene.

The source's five original outcome-blind patient folds remain fixed. Draw
source cases with replacement **within each original fold**, retaining that
fold's original draw size. Every copy of a source patient retains its original
fold. In an outer or inner split, all copies therefore move together into
training or validation; no copy of a validation patient enters that split's
training set. Do not hash synthetic copy names, reassign folds after drawing,
or stratify on expression, selected family or external performance.

Draw the external cohort's cases independently with replacement at its
original cohort size. A single source draw and a single external draw are
shared across **all genes** in a replicate. Keep the external draw identical
for all four fixed families and the selected policy. This preserves the
empirical coupling between genes and the paired comparison between models;
it does not establish an across-gene inferential procedure or independent
replications. Where a gene has missing observations, apply its original
joint-finiteness mask to the shared cohort draw instead of generating a new
gene-specific draw.

The empirical-bootstrap principle is described by
[Efron, 1979](https://doi.org/10.1214/aos/1176344552). Here it is applied to
metadata case groups conditional on the captured pairing, admitted values,
fixed cohort sizes and fixed fold partition. It does not resample tissue
sites, TMT plexes, reference material, assay measurement error, processing
versions, donor identity or the fold-assignment procedure. Cohort independence
is an assumption under the available metadata, not genotype-based proof.

## Distinct patients are different from resampling mass

There are two explicit stages of support accounting:

| Stage | Meaning of support | Policy |
| --- | --- | --- |
| Original point analysis | Distinct admitted metadata patient groups | Preserve outer training 48, inner training 32, validation 3, at least four valid outer folds and 60 common OOF groups, plus complete all-five-fold final-selection support and all four final refits. Preserve external minimum 48 distinct complete groups. |
| Bootstrap numerical replay | Integer frequency mass in a perturbed empirical distribution | Replay the same 48/32/3/4-of-5/60 computational checks on expanded rows or exactly equivalent frequency weights. Report multiplicity mass, distinct original cases and weight concentration separately. |

The second row does **not** admit repeated copies as additional independent
patients. It defines how the already chosen estimator is evaluated at a
bootstrap empirical distribution. Its mass checks are not new evidence that
the resample contains 60 distinct patients. A replica's internal legacy-shaped
count fields must never be exported without that qualification as independent
patient counts or new cohort eligibility. This distinction is explicit in
the new profile; it does not change the original fitter's point-stage gates.

Expanded-row replay is the selected implementation policy: repeat each source
row according to its draw multiplicity, retaining its original fold, and
rerun the unchanged numerical operations. This repeats median/MAD transforms,
SD fallbacks, adaptive Huber fitting, nested selection and final refits on the
resampled empirical distribution. Do not replace this with an approximately
weighted median or a different ridge normalization without a separately
specified estimator and parity tests.

For a stratum of `n` original cases drawn `n` times, the expected number of
distinct represented cases is `n * (1 - (1 - 1/n)**n)`. For source fold sizes
`15,15,14,14,14`, the total expectation is about **46.46**, despite source
frequency mass 72. An exact occupancy recurrence and convolution gives
`P(at least 60 distinct source cases) = approximately 2.025e-7`. Requiring all
original *distinct-patient* gates in every replicate would be at least this
restrictive. In 128 draws, the expected number passing even this one
distinct-60 condition is approximately `2.592e-5`. These are design-only
combinatorial calculations, not fitted or observed resampling results.
The calculation starts with `p(0,0)=1`, iterates
`p(m+1,k)=(k/n)*p(m,k)+((n-k+1)/n)*p(m,k-1)` for each fold's occupancy
distribution, then convolves the five final distributions. This makes the
strict-60 probability reproducible without measurement data.
Similarly, drawing 56 external cases 56 times represents about **35.58**
distinct external cases on average; reapplying a distinct-48 admission gate
would change the intended ordinary-bootstrap distribution.

Keep a strict-distinct feasibility diagnostic rather than silently changing
either interpretation. For every draw record, transiently, the source and
external distinct counts, unique cases within each source fold, unique cases
in each outer training set, and unique cases in each inner training set.
Summarize only aggregate minima, maxima, medians and counts of draws satisfying
the strict distinct-60/48/32/3 conditions. Those diagnostics do not reject a
draw under the declared empirical-frequency policy, add independent evidence,
or authorize lower point-stage support gates.

For nonnegative integer case frequencies `w_i`, also summarize
`(sum(w_i)**2) / sum(w_i**2)` for source/external complete support and source
training subsets. This is a **weight-concentration diagnostic**, not a proof
of effective independent sample size for adaptive Huber regression or model
selection. Distinct counts, frequency mass and this diagnostic answer
different questions and must not be substituted for one another.

## Fixed joint resampling algorithm

Request exactly **128** joint source/external draws. Order source strata by
original fold labels `0..4` and members by the frozen source plan's row order.
Within fold `h`, independently sample `n_h` indices uniformly with replacement
from its original members; concatenate the five draws. Sample external indices
uniformly with replacement from the full frozen external plan, at its original
size. Reuse these same cohort-level index draws for every gene. The identities
and draw arrays remain transient private data.

Bind separate source and external RNG streams to the new profile and one
frozen **whole-analysis** request digest, not to gene-specific seeds. The
whole request must include the original protocol/report digests, all exact
source and external locks, metadata plans, processing-boundary evidence,
original fold assignment, gene panel, current method/source hashes and the
post hoc analysis declaration. Record the seed derivation and stream names
before drawing. A code-style change must not be disguised as the same request
if its bound method changes. Identical fully bound requests must replay the
same schedule; no seed search or successful-only redraw is allowed.

For each point-eligible gene and replicate:

1. Apply the gene's original complete-case mask to the drawn source rows.
   Retain all occurrences and their original folds. Replay source nested
   evaluation with the inherited numerical mass checks, all-five-fold/all-four-
   candidate source OOF requirement, pooled individual-occurrence MAE and exact
   tie order `training_median`, `rna_only`, `cnv_only`, `full`.
2. Repeat final candidate selection using the complete common source OOF
   support, and refit all four fixed families using that draw's complete source
   occurrences. All transforms and the source-median baseline are refitted;
   all fixed refits must be available. Keep the 240-iteration equations and
   failure rules. This includes source fitting and selection *sensitivity*,
   not just coefficient perturbations around the original winning family.
3. Apply the gene's original joint-finiteness mask to the shared external draw.
   Score all four refitted fixed models and the newly source-selected policy
   on the same external occurrences. Perform no target fitting or selection.
   Use the inherited raw-coordinate MAE/RMSE definitions and the source-median
   squared-error comparator, with the median refitted in this source draw.
4. Score the **original frozen source fits and original selection** on that
   exact same external draw as a matched reference. Its source median remains
   the original frozen median. This reference is an ablation for the present
   draw schedule, not a replacement of the old conditional-only output.
5. Require source replay success and jointly finite MAE/RMSE for all fixed and
   selected models in both the refitted and frozen-reference calculations.
   One model's failure invalidates that gene's paired replicate; do not delete
   model-specific cases or retain a different external subset. Count the
   stage and reason and continue to the next of the fixed 128 attempts.

Do not call the old 128-draw external bootstrap inside each new draw. The new
outer loop itself supplies the two-cohort resampling distribution; nesting
another 128-draw loop would create a different procedure. The original
point values remain the point-estimate anchors. Neither a bootstrap mean nor
an averaged set of bootstrap predictors becomes a new deployed model.

## Failure conditioning and sensitivity ranges

Define success **per gene** using the paired criteria above. Preserve the
attempted denominator 128, the number of source/numerical/comparison failures,
and the number of successful paired replicates. The original unsupported genes
remain point-stage abstentions with no attempted rescue. Source-refit and
external-comparison failure stages remain distinguishable. Preserve inherited
reasons as reported: a source reason can combine support, numerical and
null-variation failures, and an external reason can combine insufficient
common mass and nonfinite predictions or metrics. These aggregate reasons do
not establish which individual mechanism caused a failure.

Require at least **103** successful paired replicates before producing
nominal 90% sensitivity ranges. With `K` successful draws, use order statistics
`max(1, ceil(.05*K))` and `min(K, ceil(.95*K))` without interpolation. Apply the
same successful subset to refitted and frozen-reference MAE/RMSE and endpoint
ranges. A valid frozen-reference draw excluded because source refitting failed
must not silently re-enter only the reference range. Report how many such
reference-available draws were withheld by the matched conditioning.

For R², require finite denominators for both refitted and frozen-reference
calculations and use their common paired subset, with its own 103-draw
minimum. Its availability must not suppress valid loss summaries. R² changes
include variation in the refitted source-median denominator as well as model
predictions. All missing interval results remain explicit; failed sensitivity
does not erase the original point estimate or its original acceptance state.

Because each gene can fail on a different draw, also report the aggregate
count of draws jointly successful for all point-eligible genes. Do not impose
an unannounced all-genes success gate or use different source/external draws
to improve one gene's rate. Shared schedules preserve empirical dependence;
success-conditioned marginal summaries still do not supply simultaneous
inference across genes or endpoints.

Selection frequencies must retain an explicit denominator: attempts, available
source selections and successful paired comparisons are different populations.
Record the four candidate counts and failed/unavailable count instead of
renormalizing failures away: the four available-choice counts plus unavailable
choices must sum to 128; a separately labeled successful-comparison breakdown
must sum to its paired-success count. Frequencies are algorithmic stability summaries,
not probabilities that a biological mechanism or model family is true.

## Matched frozen-fit ablation and variance identity

Retain the original endpoint signs: primary is `MAE(full) - MAE(CNV-only)`;
secondary is `MAE(selected) - MAE(full)`. For either endpoint on the **same
successful paired draws**, write:

```text
A_b = endpoint after refitting and reselecting on source draw b
B_b = endpoint from original frozen fits on the identical external draw b
D_b = A_b - B_b
sample_var(A) = sample_var(B) + sample_var(D) + 2 * sample_cov(B, D)
```

Compute variances and covariance with the same `K-1` denominator (`ddof=1`).
Report the four terms, reconstructed variance, and numerical reconstruction
error. Covariance can be negative. Do not truncate it, force nonnegative
"contributions", convert the terms into causal percentages, or claim that the
joint range must be wider than the frozen reference. `D` combines empirical
source fitting, selection and success-conditioning sensitivity; it is not an
isolated causal component of training uncertainty.

This matched reference controls the new external draw basis. The original
conditional-only intervals used their original request/seed scheme; comparing
their widths directly with the new ranges would also mix schedules and
possibly success subsets. No range-width change establishes improved
calibration, a variance partition into biological causes, or uncertainty
about every part of the experiment.

## Statistical limits and alternatives not selected

Refitting selection is necessary to expose its instability, but does not
automatically validate percentile coverage for a discontinuous selector with
hard eligibility and convergence gates. See
[Efron, 2014](https://doi.org/10.1080/01621459.2013.823775) on estimation after
model selection and
[Leeb and Pötscher, 2006](https://doi.org/10.1214/009053606000000821) on limits
of post-selection distribution estimation. These papers analyze particular
procedures and assumptions; they are not a theorem about the exact coverage
of this glioma benchmark. Here no such coverage calibration has been shown.

At 128 draws, a nominal five-percent tail contains only about 6.4 draws before
failure filtering. The percentile rank resolution is `1/K`; with only 103
successful draws it is about 0.97 percentage points. This is a bounded
engineering sensitivity policy, not evidence of precise tail estimation.
Success conditioning can itself select easier empirical samples. Persistent
failures are part of the finding, not an invitation to increase the budget,
lower support rules or redraw until the desired interval appears.

| Alternative | Why it is a different analysis |
| --- | --- |
| Require all original distinct-patient gates inside each ordinary draw | Almost all draws would be unsupported by the occupancy calculation. This is a feasibility diagnostic, not the selected bootstrap distribution. |
| Positive multiplier or Bayesian bootstrap weights | All original identities can retain positive weight, but concentration still reduces information. Weighted medians/MADs, SD fallback, ridge normalization, nested losses and a weighted solver must be fully specified and tested; reusing the unweighted fitter without those changes does not implement it. |
| Subsampling or an `m`-out-of-`n` bootstrap | Changes training size, support and potentially convergence/selection behavior; it needs a separate size/scaling policy and theoretical justification. It is not a way to bypass the existing evidence thresholds. |
| Bootstrap smoothing or model averaging | Changes the point predictor and target procedure. This profile keeps the original point policy and does not introduce a better-default claim. |
| Plex/site or donor clusters | Requires an admitted cluster crosswalk, enough independent clusters, and a different sampling design. Case resampling alone does not model those dependencies. |

[Rubin's Bayesian-bootstrap paper](https://doi.org/10.1214/aos/1176345338)
defines a different random empirical-distribution construction and inferential
interpretation; it is an alternative requiring explicit assumptions, not a
guarantee that positive weights solve small-sample or post-selection inference.

The present ranges remain conditional on observed provider outputs, historical
processing, complete-case inclusion, empirical case distributions, fixed fold
partition, frozen family/loss/solver and metadata independence assumptions.
They exclude reference-lot and measurement error, batch uncertainty, population
shift beyond the two empirical cohorts, protocol-development choices and
uncertainty from the earlier decision to conduct this post hoc analysis.
The new profile makes no causal, clinical, molecular-class, biomarker-novelty,
FDR, aligned-validation or default-promotion claim.

## Implementation and release requirements

Keep the frozen original `transfer.py` and its profile/results intact. The
additive implementation must have its own source and method digests and bind
the original protocol/report. Include explicit fields separating original
unique-group eligibility, bootstrap frequency mass, distinct-count diagnostics,
weight-concentration diagnostics, fixed-fold conditioning, repeated source
selection, matched reference conditioning and unvalidated nominal coverage.

Before a real run, synthetic tests must verify duplicate patient copies never
cross training/validation roles; identity draws reproduce original fits;
source transforms, all nested choices and all final models are refitted;
external values never enter fitting; all genes share both cohort draws; all
models share external cases; original abstentions remain abstentions; source
and target mass/unique counts differ honestly; and failures are not redrawn.
Independent arithmetic oracles must check the 103/128 boundary, nearest ranks,
candidate-frequency denominators, R² paired availability and the variance
identity with positive, zero and negative covariance. Point metrics and old
artifacts must remain unchanged.

Persist only aggregate receipts and whole-request/draw-schedule digests.
Case IDs, copy IDs, source/external index draws, fold memberships, fitted
coefficient vectors, individual predictions and residuals stay private and
transient. All real-data derivatives remain `local_only_terms_unverified`,
outside Git and uploads. Deterministic replay and independent aggregate,
statistical-scope and privacy review are required before local packaging.
