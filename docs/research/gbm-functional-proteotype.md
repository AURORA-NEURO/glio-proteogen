# GBM functional-proteotype concordance

`migliozzi-gbm-functional-proteotype/1.0.0` is a synchronous, stateless research
model that compares a caller-supplied bulk-protein contrast with four functional
proteotype signatures reported for CPTAC glioblastoma:

- glycolytic/plurimetabolic (`GPM`);
- mitochondrial (`MTC`);
- neuronal (`NEU`); and
- proliferative/progenitor (`PPR`).

It emits four relative, continuous source-axis concordance coordinates. It does not
choose a winning subtype and does not emit subtype probabilities, cell fractions,
pathway activity, diagnosis, prognosis, treatment response, or treatment guidance.

## Exact source and admitted scope

The source is Migliozzi et al., “Integrative multi-omics networks identify PKCδ
and DNA-PK as master kinases of glioblastoma subtypes and guide targeted cancer
therapy,” *Nature Cancer* (2023),
[DOI 10.1038/s43018-022-00510-x](https://doi.org/10.1038/s43018-022-00510-x),
PMCID `PMC9970878`. The article and supplement are available under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), subject to source
credit lines for third-party material.

The builder verifies the 7,635,280-byte supplementary workbook at SHA-256
`865a2db1ec99dcf047d6ff56b313a21607b840e5239bb9184739f6f6f217fb88`.
It admits only aggregate source lists:

- Supplementary Table 2d: 150 source-ranked proteins for each of the four axes;
- Supplementary Table 2e: 243 GPM, 107 MTC, 272 NEU, and 204 PPR source-cohort
  pathway rows.

No patient identifier, sample identifier, per-sample measurement, or
patient-by-feature matrix is bundled. Exact worksheet locks, row counts, source
field semantics, catalog digests, attribution, and the reproducible import command
are documented in
[`gbm-functional-proteotype-source.md`](gbm-functional-proteotype-source.md).

The repository implementation was started from upstream `main` commit
`b0339c55e1efad82997caefe8ffe030389f0e23e` and developed on
`feature/research-evidence-graph`. This code baseline is recorded separately from
the scientific workbook provenance above.

## Request and evidence states

A request supplies an opaque sample ID, an explicit effect-reference ID, and up to
4,096 unique protein observations on the
`standardized_log2_abundance_contrast` scale. An exact Table 2d gene symbol is
required for `observed`, `left_censored`, and `missing` declarations. An unresolved
symbol is permitted only when explicitly `unsupported`. Duplicate observation IDs
or gene symbols are rejected.

The evidence state controls numerical meaning:

- `observed` supplies a point effect, positive standard error, positive quality
  weight, and provenance digest;
- `left_censored` supplies an upper detection limit with its limit uncertainty,
  positive quality, and provenance digest;
- `missing` carries no effect or error and requires zero quality; and
- `unsupported` carries no effect or error and requires zero quality.

Source-mapped missing and unsupported declarations remain visible in axis evidence
counts; unresolved unsupported symbols remain visible in the complete request receipt.
Neither enters the objective, rank background, bootstrap perturbations, or drivers, and
neither can alter a deterministic random stream. Requested replicate counts extend a
common random prefix rather than selecting a new seed. Inactive evidence is not converted
into zero or negative evidence.

## Equality-constrained robust model

For source protein \(i\), let \(a(i)\) be its source axis, \(m_i\) its Table 2d
MWW score, \(x_i\) the caller effect or censoring limit, \(\sigma_i\) its
standard error, and \(q_i\) its quality weight. The fixed source loading is

\[
\ell_i=\frac{m_i}{\operatorname{median}_{j:a(j)=a(i)}m_j}.
\]

For intercept \(b\) and four axis coordinates \(\theta_a\), the fitted value is

\[
f_i=b+\ell_i\theta_{a(i)},\qquad \sum_a\theta_a=0.
\]

The equality constraint makes the four coordinates relative contrasts; a common
offset in every observation is absorbed by \(b\). It is not evidence of absolute
activation. With \(s_i=\sqrt{\sigma_i^2+0.25^2}\), an observed residual is
\((f_i-x_i)/s_i\). For a left-censored upper limit \(u_i\), the residual is zero
when \(f_i\leq u_i\) and \((f_i-u_i)/s_i\) otherwise. The optimized objective is

\[
\sum_i q_i\rho_{1.345}(r_i)
+\frac{10^{-6}}{2}b^2
+\frac{10^{-4}}{2}\sum_a\theta_a^2,
\]

where \(\rho\) is Huber loss. A positive, nonbinding censor limit therefore cannot
pull an axis negative. Censoring is preserved as a one-sided constraint rather than
imputed as a low observation.

The implementation solves the five-parameter convex problem by deterministic IRLS
with an explicit KKT equality constraint. Candidate steps use monotone backtracking
with factor `0.5`; accepted steps cannot increase the checked objective. Convergence
requires maximum coordinate change at most `1e-8` and projected-gradient norm at
most `1e-7`, within 64 iterations. The result includes every baseline, candidate,
accepted objective, damping decision, convergence state, gradient norm, and a digest
of the complete solver trace. This is a joint numerical optimization, not four
weighted-average formulas.

## Independent competitive-rank evidence

The second estimator uses only exact `observed` effects. For every axis it compares
the observed signature proteins with observed proteins declared from the other three
fixed signatures. Average ranks preserve exact ties; the reported statistic is the
tie-corrected Mann–Whitney U and rank-biserial effect.

The joint rank family is estimable only when every axis has at least three observed
signature proteins, every complement has at least twenty observed proteins, and the
observed effects are not all tied. Each deterministic null replicate shuffles the
four axis labels only within source-rank quartiles while retaining the request's
per-quartile coverage. One joint shuffle produces all four null statistics. Two-sided
empirical p-values use a plus-one correction, and Benjamini–Hochberg adjustment is
applied once to the fixed family `GPM`, `MTC`, `NEU`, and `PPR`. The default is 256
permutations; requests may choose 64 through 2,048.

This rank comparison is computationally distinct from the robust location fit, but
it uses the same submitted observations and source signatures. It is not an
independent cohort or external biological validation.

## Deterministic uncertainty and classification

The default uncertainty calculation performs 64 joint bootstrap perturbations;
requests may choose 16 through 256. Every active point or censor limit receives an
independent normal perturbation at its caller-supplied standard error and retains its
original evidence state. Each successful replicate refits the complete constrained
four-axis model from the point solution. The four coordinates therefore remain on
one shared replicate track rather than being assembled from unrelated draws.

Separate seeds derive from a numerical stream identity (profile version, constants,
NumPy version, and signature-catalog semantics) plus exactly the evidence each stream
consumes. Bootstrap identity includes active effects, censor states, errors, and quality;
permutation identity includes only observed gene/effect ranks. Replicate counts are
excluded so a larger run extends the same random prefix. Observation order, inactive
declarations, opaque sample and observation IDs, effect-reference labels, provenance
labels, and source comments do not change numerical streams. The complete profile still
binds normalized behavior-defining source text. Results and traces are quantized to six
decimal places for stable replay.

At least sixteen converged bootstrap refits are required. The 5th and 95th
percentiles form a nominal 90% interval, widened if necessary to contain the point
estimate. Classification uses the entire interval:

- `source_aligned` only when the lower bound is above `+0.25`;
- `source_opposed` only when the upper bound is below `-0.25`;
- `neutral` only when the interval lies wholly inside `[-0.25,+0.25]`;
- otherwise `indeterminate`; and
- `not_estimable` after abstention.

The interval is a deterministic sensitivity interval under the submitted fixed
standard errors. It does not estimate cross-protein covariance, batch effects,
between-sample biological variance, tumor purity, or external calibration.

## Support and explanations

An axis abstains when fewer than six active signature proteins are supplied, a joint
solver result is not accepted, or fewer than sixteen bootstrap refits converge.
Otherwise it is at least `limited`. `supported` additionally requires:

- at least 15 active and at least 10 exactly observed signature proteins;
- at least 10% active coverage of the fixed 150-protein signature;
- reliability-weighted effective sample size at least 8, where
  \(n_\mathrm{eff}=(\sum w_i)^2/\sum w_i^2\) and
  \(w_i=q_i/(\sigma_i^2+0.25^2)\);
- at least 80% bootstrap convergence;
- estimable competitive-rank evidence with fixed-family `q <= 0.10`; and
- agreement between the signs of the latent and rank-biserial estimates.

Every estimable axis reports exact state counts, active coverage, effective sample
size, bootstrap direction stability, fit/rank discordance, and up to eight auditable
protein drivers. Drivers retain request observation identity, exact source rank and
label, evidence state, reliability, loading, and its Huber-capped score contribution to
the raw axis gradient at the joint solution. A non-binding left-censored value has zero
score. These are local residual-pressure explanations, not causal protein importance,
leave-one-out effects, or leverage-corrected influence.

Three ablation families refit the complete constrained model:

- remove each represented source-rank quartile;
- remove each represented active evidence state; and
- leave out each reported top driver.

Each ablation reports the removed count, support after removal, point-estimate delta,
or an explicit abstention reason. Its classification is deliberately `indeterminate`:
the ablation refit does not run a second bootstrap interval, so the interval-only state
rules cannot be applied. Ablation support rechecks active, observed, fractional, and
effective-sample-size gates; it is not a new bootstrap or external validation.

## Table 2e source context is not sample inference

Each axis returns the first eight Table 2e rows in source worksheet order with the source
pathway name, logitNES, p-value, q-value, and row ordinal. Every row is explicitly marked
`sample_inference_status: not_evaluated` and
`interpretation: source_cohort_pathway_context_only`.

Table 2e rows never enter the robust objective, rank comparison, bootstrap,
classification, support gate, driver score, or ablation. The catalog does not contain
pathway membership topology or a sample-level pathway measurement, so the runtime
cannot silently turn source-cohort enrichment into a pathway claim for the submitted
sample. Cross-axis pathway-label overlap is retained as source context.

## Profile, replay, and interfaces

The profile binds NumPy `2.5.2`, all constants and limits, normalized source text for
canonicalization, catalog loading/validation, contracts, engine, solver, and rank
implementations, the catalog byte and semantic digests, per-axis signature/pathway
digests, source workbook digest, and the versioned synthetic demo request. The request,
profile, solver trace, and complete result each have content digests. Requests and
results are never persisted server-side.

HTTP operations:

- `GET /v1/research/gbm-functional-proteotype/profile`
- `GET /v1/research/gbm-functional-proteotype/demo`
- `POST /v1/research/gbm-functional-proteotype/analyze`
- `POST /v1/research/gbm-functional-proteotype/verify`

Matching commands:

```text
glio-proteogen gbm-functional-proteotype profile
glio-proteogen gbm-functional-proteotype demo
glio-proteogen gbm-functional-proteotype analyze request.json
glio-proteogen gbm-functional-proteotype verify replay-envelope.json
```

Analysis requests and results are capped at 2 MiB; replay envelopes are capped at
4 MiB. The HTTP adapter admits two concurrent computations per process, applies a
120-second deadline, parses and bounds the body before acquiring compute capacity,
propagates caller disconnect cancellation, rejects duplicate
JSON keys and non-finite numbers, and returns sanitized errors without echoing input.
Replay recomputes the exact request and checks request, profile, result, solver-trace,
and complete semantic equality.

The versioned demo contains 108 synthetic declarations over exact source genes: 24
observed proteins plus one censored, one missing, and one unsupported declaration for
each axis. It uses 64 bootstraps and 256 permutations and contains no patient data.
The executable benchmark runs this full demo repeatedly in a fresh uninstrumented
process, rejects result-digest or result-size drift, and requires analysis p95 below
two seconds. It is a software regression gate, not biological validation.

```bash
python -m benchmarks.research_gbm_functional_proteotype --warmup-runs 1 --measured-runs 5
```

## Scientific self-consistency oracles

The deterministic synthetic oracle suite checks five deliberately narrow properties:
Huber resistance to one gross outlier relative to an effectively uncapped quadratic fit;
binding versus nonbinding one-sided censor limits; inverse-error behavior under constructed
heteroscedastic perturbations plus the expected propagation of common-mode and axis-block
correlated shifts; Monte Carlo rank-null output against an independently exhaustive small
stratified permutation space; and the robust censored solution against a test-only black-box
convex mesh search. SciPy is not part of the locked dependency graph, so that last oracle
uses only objective evaluations and does not reproduce the production IRLS/KKT solve.

These checks are software and scientific self-consistency tests on artificial inputs. The
heteroscedastic check establishes only that submitted standard errors affect relative
weighting. The correlated checks show that a common shift is absorbed by the intercept and
that axis-block correlation can bias the axis coordinates; they do not validate covariance
modeling or interval coverage. None of the oracles uses an external cohort or establishes
biological, platform, clinical, prognostic, predictive, or treatment validity.

## Limitations and claim ceiling

- Table 2d proteins and Table 2e pathways were selected in the source CPTAC-GBM
  cohort; concordance is not independent validation of those discoveries.
- The Table 2d MWW values are source ranking scores, not probabilities or calibrated
  effects. Median-normalized loadings are a declared GLIO-PROTEOGEN interpretation.
- Exact source gene labels are required; this lane does not silently normalize aliases
  or infer protein groups from raw peptides.
- Input effects are caller-standardized bulk-tumor contrasts. The model does not
  deconvolve malignant cells, immune/stromal admixture, neuronal contamination, tumor
  purity, batch, platform, or treatment history.
- The sum-to-zero coordinates are relative source-axis contrasts. They are not
  absolute pathway or cellular activities, fractions, probabilities, or a categorical
  subtype assignment.
- The perturbation interval assumes independent caller-supplied fixed errors and does
  not establish nominal coverage in an external cohort.
- Locked simulations exercise idealized self-consistency and software calibration; they
  do not establish biological validity under correlated, censored, heteroscedastic, or
  platform-shifted real proteomes.
- Exact replay is scoped to the pinned Python 3.12.13/NumPy 2.5.2 container image.
  Cross-platform BLAS/LAPACK bit parity is not claimed.
- Observation provenance digests are caller-declared receipts, not server-verified
  source artifacts; the complete request preserves the observation-to-digest mapping.
- Source pathways are displayed only as historical cohort context because membership
  topology and sample-level pathway evidence were not admitted.
- No output is clinically validated, prescriptive, or suitable for automated action.
