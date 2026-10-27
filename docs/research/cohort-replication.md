# Aggregate glioma cohort replication

`glioma-cohort-replication/1.0.0` combines caller-supplied cohort effect
summaries for one declared glioma domain, estimand, contrast, and effect scale.
It computes inverse-variance fixed-effect and DerSimonian--Laird random-effects
summaries, heterogeneity, approximate prediction intervals, leave-one-cohort-out
diagnostics, and fixed-family multiple-testing adjustments. It is an additive
research lane, separate from the governed module contracts.

Every estimable feature remains `limited`; features with fewer than two
observed cohorts are `abstained`. The executable methods are conventional
meta-analysis methods. Their implementation does not establish scientific
novelty, authenticate a cohort, validate a supplied standard error, or complete
an independent glioma replication study. No empirical statistical calibration
or real-data replication result is supplied by this lane. The bundled demo is
synthetic and cannot supply biological validation.

## Question, unit of analysis, and scope

The computational question is: how do compatible, independently declared
cohort-level estimates agree, how uncertain is their weighted summary, and how
sensitive is that summary to cohort omission? The unit of analysis is one
cohort's aggregate effect for one feature. Participant rows, expression
matrices, sample identifiers, sequences, and new patient measurements are not
inputs.

The request has one `disease_context`, chosen from
`glioblastoma_idh_wildtype`, `astrocytoma_idh_mutant`,
`oligodendroglioma_idh_mutant_1p19q_codeleted`, or `other_glioma`. This is a
caller declaration, not a diagnosis inferred by the engine. A broad
`other_glioma` declaration cannot make biologically incompatible populations
exchangeable. Historical source labels and observed molecular status should be
reconciled before constructing an input, with unknown status retained rather
than guessed. The molecular categories are grounded in the
[WHO CNS5 author summary](https://pmc.ncbi.nlm.nih.gov/articles/PMC8328013/).

An `estimand_id` must identify the same statistical quantity in every cohort:
outcome definition, predictor or group contrast, reference direction,
conditioning covariates, effect construction, and sampling unit. The free-text
`contrast` records its scientific interpretation. Equality of an identifier or
scale name is necessary bookkeeping, not a machine-verified guarantee that
these definitions agree.

## Strict input contract

The authoritative Python contracts live in
[`contracts.py`](../../src/glio_proteogen/research/cohort_replication/contracts.py).
`ReplicationRequest` accepts these top-level fields:

| Field | Required meaning |
| --- | --- |
| `schema_version` | `1.0.0` |
| `analysis_id` | Opaque analysis identifier |
| `disease_context` | One of the four declared domains above |
| `estimand_id` | Shared, prespecified effect definition |
| `effect_scale` | One of the four supported scales below |
| `contrast` | Shared direction and scientific contrast |
| `independence_basis` | `caller_declared_disjoint_participants` |
| `cohorts` | Two through sixteen cohort receipts |
| `features` | One through 256 predeclared feature hypotheses |

Each cohort receipt contains `cohort_id`, `label`, `source_sha256`,
`independence_group`, and `sample_size`. Sample size is an integer from two to
1,000,000. The digest format is `sha256:` followed by 64 lowercase hexadecimal
characters. Cohort IDs, source digests, and independence groups must each be
unique. Cohorts with a repeated source digest or repeated independence group
are rejected conservatively, even when their labels differ.

The caller must resolve participant overlap before submission. All cohorts
connected by known or possible overlap must share the same independence group
and therefore cannot appear together in this version's request. Assigning
different group strings does not prove independence. The engine cannot detect
undisclosed overlap, shared controls, repeated recruitment, related
participants, or correlated estimates from different analyses of the same
people. It does not authenticate the source bytes named by a supplied digest.

Each feature contains `feature_id`, `label`, and exactly one effect for every
declared cohort. Its effect has `cohort_id` and `state`:

- `observed` requires a finite `estimate` in [-100, 100] and a finite
  `standard_error` in [0.000001, 100]. The standard error belongs to the effect
  estimate on the declared analysis scale, not to participant measurements.
- `missing` and `unsupported` require both numerical fields to be absent or
  null. Neither state contributes a zero effect, weight, or direction vote.

Duplicate feature IDs, duplicate or absent cohort effects, unexpected members,
non-finite values, invalid state/number combinations, and out-of-bound values
fail validation. The engine canonicalizes cohort, feature, and effect order by
their identifiers before computing request digests.

### Compatible effect scales

| `effect_scale` | Required construction and comparison |
| --- | --- |
| `standardized_mean_difference` | The same group direction, standardization denominator, bias correction, and compatible SE definition; Cohen's d and Hedges' g must not be silently mixed. |
| `log2_ratio` | The same numerator/reference, log base, feature definition, and biological quantity; a ratio of means and a mean of log ratios are different estimands. |
| `fisher_z` | Fisher-transformed correlation with the same association type and conditioning; supply SE on the z scale. Ordinary Pearson, rank, and partial correlations cannot be mixed merely by transformation. |
| `standardized_regression_coefficient` | The same outcome/predictor standardization and covariate specification; all standardization must be performed inside the appropriate training folds when prediction is evaluated. |

The service does not transform between scales or back-transform Fisher z to a
correlation. It tests a zero effect on the submitted analysis scale. It accepts
no raw-regression-slope scale. FPKM-UQ RNA, TPM, normalized protein ratios,
absolute abundance, and phosphosite measures cannot be subtracted or pooled
solely because they refer to the same gene.

In particular, the existing local
[`cptac-gbm-transcript-protein-discordance`](cptac-gbm-transcript-protein-discordance.md)
artifact is not automatically an admitted replication input. Its source-scale
conditional coefficient and nominal percentile-bootstrap intervals do not
provide a validated standardized coefficient/SE conversion. Do not obtain an
SE by dividing an asymmetric bootstrap interval width by a normal constant,
relabel its raw slope, or treat its source-cohort folds as independent cohorts.
A future adapter must derive the prespecified effect and valid sampling
uncertainty from each admitted cohort under a separately tested protocol.

## Exact statistical procedure

For one feature, let `k` be the number of observed cohort effects, `y_i` their
estimates, and `s_i` their supplied standard errors. Missing and unsupported
cohorts remain in coverage accounting but are excluded from these sums.
The methods assume independent approximately normal cohort estimates and
appropriately estimated within-cohort variances. They do not re-estimate those
variances from the declared sample sizes.
The random-effects interpretation further assumes compatible cohort effects
are exchangeable around a shared mean; its approximate prediction interval
also uses a normal distribution for those underlying effects. Different
populations or estimands cannot be made exchangeable by adding tau squared.

### Pooling and heterogeneity

For `k >= 2`, define fixed-effect weights and summary:

```text
w_i = 1 / s_i^2
mu_FE = sum(w_i * y_i) / sum(w_i)
SE_FE = sqrt(1 / sum(w_i))
Q = sum(w_i * (y_i - mu_FE)^2)
df = k - 1
C = sum(w_i) - sum(w_i^2) / sum(w_i)
tau^2_DL = max(0, (Q - df) / C)
I^2_percent = 0                         if Q = 0
             100 * max(0, (Q-df) / Q)  otherwise
```

The fixed-effect model summarizes a common-effect assumption; it does not
demonstrate that the cohorts share a single biological effect. The
DerSimonian--Laird method-of-moments estimate introduces nonnegative
between-cohort variance:

```text
v_i = 1 / (s_i^2 + tau^2_DL)
mu_RE = sum(v_i * y_i) / sum(v_i)
SE_RE = sqrt(1 / sum(v_i))
```

For both summaries, the nominal 95% interval and two-sided p-value use a
standard normal reference, with `z_0.975 = 1.959963984540054`:

```text
interval = mu +/- z_0.975 * SE
p = 2 * (1 - Phi(abs(mu / SE)))
```

The implementation evaluates the normal tail using the complementary error
function. No chi-square p-value for Q, confidence interval for tau squared,
Hartung--Knapp adjustment, REML estimator, meta-regression, covariance-aware
pooling, or publication-bias model is implied. See the
[DerSimonian and Laird method](https://doi.org/10.1016/0197-2456(86)90046-2).

These intervals condition on estimated heterogeneity and on the supplied
within-cohort SEs. Normal intervals can undercover, especially with few
cohorts, unequal precision, or meaningful heterogeneity; `tau_squared=0` and
`i_squared_percent=0` do not prove homogeneity. This limitation is supported by
[simulation work on few-study random-effects inference](https://pmc.ncbi.nlm.nih.gov/articles/PMC4647507/).
The current calculation remains explicitly nominal and exploratory at small
`k`.

### Prediction interval and cohort influence

Only for `k >= 3`, the engine adds:

```text
approximate PI = mu_RE +/- z_0.975 * sqrt(tau^2_DL + SE_RE^2)
```

Its method is `approximate_normal_random_effects`. It describes a hypothetical
compatible cohort's underlying effect under the random-effects assumptions;
it is not an individual-patient interval or a calibrated guarantee for a new
institution. Three cohorts are an operational computation gate, not evidence
that the approximation is reliable at that sample size.

For the same `k >= 3` gate, each leave-one-out entry removes one observed
cohort, re-estimates heterogeneity and the random-effects summary using the
remaining cohorts, and records the difference from the complete summary.
`delta_estimate` is the omitted-cohort summary minus the complete summary.
Missing cohorts are not omitted to create artificial influence runs. With two
observed cohorts, leave-one-out and prediction intervals are absent. A stable
omission result cannot establish robustness to unobserved populations or shared
bias.

### Direction agreement

Direction counts use the signs of observed point estimates, with exact zero
retained separately. The majority fraction is a descriptive count statistic;
it is `max(positive_count, negative_count, zero_count) / observed_count`, or
null when no cohort is observed. It does not weight cohort precision or
represent a calibrated probability.
The classifications are:

- `all_nominal_intervals_positive`: at least two cohorts are observed and
  every observed cohort's normal 95% interval is above zero;
- `all_nominal_intervals_negative`: at least two cohorts are observed and
  every such interval is below zero;
- `mixed_directions`: observed point estimates include positive and negative
  directions; or
- `direction_indeterminate`: the remaining cases.

A direction label is not a replication significance test. Inspect the number
of observed cohorts, intervals, heterogeneity, and influence together.

### Fixed-family BH and BY adjustments

The input `features` list is the complete prespecified hypothesis family of
size `m`. Each estimable feature contributes its random-effects two-sided
normal p-value. An abstained feature contributes `p=1` to the family and
retains both adjusted values at one; its raw result p-value remains null.
Removing abstentions after seeing results would change the denominator and is
outside this protocol.

Sort the family p-values increasingly as `p_(j)` for ranks `j=1,...,m`.
Benjamini--Hochberg adjusted values are the reverse cumulative minima of
`min(1, m*p_(j)/j)`. The additional Benjamini--Yekutieli values replace `m`
with `m*H_m`, where `H_m=sum(1/j, j=1,...,m)`. Restore feature identity after
adjustment. `adjusted_p_value` is BH;
`dependence_robust_adjusted_p_value` is BY. These are adjusted p-values, not
posterior probabilities or measured false discovery proportions.

BH relies on valid input p-values and suitable dependence conditions. Gene,
pathway, and protein-complex hypotheses often share measurements and are
correlated; this service does not verify the required dependence structure.
BY addresses arbitrary dependence under valid marginal p-values, but cannot
repair invalid SEs, small-k normal approximations, selection bias, undisclosed
overlap, or an outcome-selected family. It can also be substantially more
conservative. See [Benjamini and Hochberg, 1995](https://doi.org/10.1111/j.2517-6161.1995.tb02031.x)
and [Benjamini and Yekutieli, 2001](https://doi.org/10.1214/aos/1013699998).

## Results, replay, and operational limits

`ReplicationResult` returns the declared context, cohort receipts, family size,
feature-level summaries and reasons, and profile/request/result digests. Each
feature retains its original typed cohort effects, observed and total counts,
`fixed_effect`, `random_effect`, `heterogeneity`, `prediction_interval`,
`p_value`, the two adjusted values, `leave_one_out`, and `direction_agreement`.
No aggregate fit is emitted when fewer than two observed effects are available.

The result explicitly has `contains_participant_data=false`; callers must keep
identifiers and labels free of participant identifiers. Digest-bound replay
proves the submitted objects reproduce the same calculation under the bound
profile. It cannot prove that a source is authentic, a summary was correctly
extracted, participants are disjoint, the family was selected prospectively,
or the scientific model is valid. No state promotes output to a governed
module, a causal mechanism, clinical classification, or treatment advice.

The request, result, and replay bounds are respectively 2 MiB, 4 MiB, and
8 MiB. The HTTP adapter allows two concurrent computations with a 30-second
deadline and bounded JSON bodies; it returns sanitized failures. These are
operational limits, not validated scientific sample-size requirements.

## API and CLI workflow

The mounted research prefix is `/v1/research/cohort-replication`:

| Method and suffix | Operation |
| --- | --- |
| `GET /profile` | Inspect methods, assumptions, bounds, and semantic/profile digests |
| `GET /demo` | Obtain a synthetic request, not real glioma evidence |
| `POST /analyze` | Submit a strict `ReplicationRequest` as `application/json` |
| `POST /verify` | Submit a replay envelope with `request` and `result` |

The CLI mirrors these operations and writes canonical JSON to standard output:

```text
uv run glio-proteogen cohort-replication profile
uv run glio-proteogen cohort-replication demo
uv run glio-proteogen cohort-replication analyze work/replication-request.json
uv run glio-proteogen cohort-replication verify work/replication-envelope.json
```

The following is a shape template. Replace angle-bracket placeholders with
source-verified cohort metadata and prospectively defined effect summaries;
it is deliberately not a runnable data example. A missing effect is retained
in the rectangular family.

```json
{
  "schema_version": "1.0.0",
  "analysis_id": "analysis.independent-cohorts",
  "disease_context": "glioblastoma_idh_wildtype",
  "estimand_id": "estimand.prespecified-protein-group-contrast",
  "effect_scale": "log2_ratio",
  "contrast": "<same numerator/reference and covariate specification>",
  "independence_basis": "caller_declared_disjoint_participants",
  "cohorts": [
    {
      "cohort_id": "cohort.a",
      "label": "<source cohort A>",
      "source_sha256": "sha256:<64 lowercase hex characters for source A>",
      "independence_group": "participants.a",
      "sample_size": "<integer count of independent participants>"
    },
    {
      "cohort_id": "cohort.b",
      "label": "<independent source cohort B>",
      "source_sha256": "sha256:<64 lowercase hex characters for source B>",
      "independence_group": "participants.b",
      "sample_size": "<integer count of independent participants>"
    }
  ],
  "features": [
    {
      "feature_id": "feature.prespecified-a",
      "label": "<feature A>",
      "effects": [
        {
          "cohort_id": "cohort.a",
          "state": "observed",
          "estimate": "<finite effect estimate>",
          "standard_error": "<positive SE on the same scale>"
        },
        {"cohort_id": "cohort.b", "state": "missing"}
      ]
    }
  ]
}
```

Save the accepted request and returned result without editing their scientific
contents. The verification envelope is an object of this shape:

```json
{"request": "<complete request object>", "result": "<complete result object>"}
```

Those quoted placeholders must be replaced by JSON objects, not stringified
JSON. Use the synthetic demo to exercise transport, rendering, and replay
before constructing a real analysis. A successful synthetic run verifies
software behavior only.

## Real-data benchmark and release evidence still required

A real replication claim needs an admitted extraction protocol in addition to
this aggregate calculator:

1. Freeze the hypothesis family, estimand, cohort inclusion rules, disease
   domain, missingness policy, effect construction, and SE estimator before
   examining validation outcomes. Record source versions and participant
   overlap evidence, including repeated specimens and shared controls.
2. Verify cohort bytes and metadata, molecular-class scope, biospecimen
   matching, platform units, reference/contrast orientation, batch processing,
   and reuse terms. PDC human-readable study IDs resolve to the newest version
   by default; record the version-specific UUID and exact file digests. See
   the [official PDC API documentation](https://pdc.cancer.gov/pdc-docs/api-documentation).
3. Derive compatible per-cohort effects/SEs with audited independent or
   patient-clustered sampling uncertainty. Keep fitting, preprocessing,
   covariate selection, tuning, and feature selection inside the appropriate
   training folds. Treat all specimens from a participant as one group.
4. Publish arithmetic oracles and independent implementation comparisons for
   pooling and adjustments; null simulations for false positive behavior;
   heterogeneous, correlated-feature, overlap, unequal-precision, and missing
   evidence stress cases; and interval-coverage simulations across small and
   larger k. Do not mistake replay checks for statistical calibration.
5. Evaluate source-held-out direction and predictive benefit using matched
   baselines and common support. Retain negative results, omitted cohorts,
   abstentions, and sensitivity to cohort/covariate/feature-family choices.
   Report exploratory meta-analysis separately from frozen external testing.

[Wang et al., 2021](https://pmc.ncbi.nlm.nih.gov/articles/PMC8044053/) provides
the initial CPTAC GBM discovery context. [Liu et al., 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11337243/)
reports an independent high-grade glioma cohort with primary/recurrent
specimens and is a candidate replication source after admission. This document
does not assert that either cohort has already been processed into compatible
inputs for this lane. Transport of conditional RNA--protein associations after
composition adjustment is a testable hypothesis, not an established result.

The phased [glioma frontier roadmap](glioma-frontier-roadmap.md) separates
these validation tasks from later spatial, longitudinal, proteoform, and
training-scale expansion.

## Operational benchmark

Run `uv run python tools/benchmark_cohort_replication.py --repeats 5` to
measure the fully observed 256-feature by 16-cohort synthetic panel. The report
separates warm-analysis timings, one replay, payload sizes, and a separate
Python-traced allocation measurement. These are local operational measurements,
not a biological accuracy benchmark or a distributed scaling result.
