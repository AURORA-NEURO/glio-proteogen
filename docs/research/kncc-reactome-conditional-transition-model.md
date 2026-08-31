# KNCC Reactome conditional-transition fitted model

## Status and claim ceiling

`kncc-reactome-conditional-transition/1.0.0` is a research-only fitted protein-transition
concordance model. It projects caller-supplied, consecutive log2 protein-abundance changes
onto one global KNCC recurrence coordinate and ten Reactome membership coordinates after
removing their fitted global component.

The outputs are **not** pathway activation, pathway flux, causal mechanism, tumor evolution,
recurrence prediction, prognosis, treatment response, or treatment advice. The locked
evaluation is same-cohort reconstruction, not external validation. A runtime `supported`
label means that the numerical support gates passed for that request; it does not raise the
scientific evidence beyond this claim ceiling.

The model uses only the admitted PDC000514/KNCC protein feature axis and the exact Reactome
release 97 catalog described in
[`kncc-reactome-conditional-transition-source.md`](kncc-reactome-conditional-transition-source.md).

## Fitted source representation

For source patient group \(i\) and protein \(g\), the fitted transition is

\[
D_{ig} = T2_{ig}^{\mathrm{recurrent}} - T1_{ig}^{\mathrm{primary}},
\]

where both values are PDC000514 `Unshared Log` log2 protein-abundance ratios. Every training
statistic is refit within each held-patient fold.

For each gene, a robust location \(\mu_g\), robust scale \(s_g\), and finite support \(n_g\)
are fitted. The source effect is

\[
e_g = \frac{\mu_g}{s_g}\sqrt{\frac{n_g}{n}},
\]

subject to 60% training coverage. Location fitting uses Huber \(k=1.345\), at most 32
iterations, tolerance \(10^{-10}\), MAD consistency constant 1.4826, and a scale floor from
the tenth percentile with an absolute minimum of \(10^{-4}\).

Let \(U=1872\) be the union of the ten pathway member sets and \(d_g\) the number of fixed
panel pathways containing gene \(g\). The global loading is

\[
b_0 = e / \lVert e \rVert_2.
\]

For pathway \(p\), the raw degree-corrected member vector is

\[
a_{pg} = 1[g\in p] 1[g\text{ eligible}]\frac{e_g}{\sqrt{d_g}}.
\]

Its global component is removed exactly:

\[
\gamma_p=b_0^\top a_p,\qquad
c_p=a_p-\gamma_p b_0,\qquad
b_p=c_p/\lVert c_p\rVert_2.
\]

The stored design is \(B=\sqrt U[b_0,b_1,\ldots,b_{10}]\). This makes the conditional
coordinates explicit rather than treating ten highly correlated, independent pathway averages
as separate findings. In the held-patient source evaluation, naive pathway/global Spearman
correlations range from 0.7215 to 0.9688 and the largest naive pathway-pair correlation is
0.9860.

## Leakage-safe evaluation

The evaluation protocol is fixed before release:

1. Assign 104 strict patient groups to eight balanced deterministic outer folds using salt
   `kncc-reactome-panel-outer-v1`.
2. Refit all robust locations, scales, eligibility, global loadings, pathway loadings, and
   residualization using only the seven training folds.
3. Within each held patient, assign union genes to five deterministic gene folds using
   `kncc-reactome-gene-fold-v1`.
4. Fit coordinates on the other four gene folds and score predictions only on the held gene
   fold.
5. Compare zero, global-only, full global-plus-conditional, and each leave-pathway-out design.

This produces 520 patient/gene-fold evaluations. Locked aggregate results are:

| Quantity | Value |
|---|---:|
| Zero median standardized MAE | 0.7108931329 |
| Global-only median standardized MAE | 0.5622984198 |
| Global + conditional median standardized MAE | 0.5554163035 |
| Median relative MAE improvement over global | 1.20459348% |
| Evaluations improved | 66.53846154% |
| Median relative RMSE improvement | 0.36626956% |
| Patient-cluster median improvement | 1.29728555% |
| Descriptive patient-cluster 90% interval | 0.85182357% to 1.78616382% |
| Reference design condition number | 5.2021989549 |
| Outer-fold condition range | 5.1651525999 to 5.3525550754 |
| Minimum outer-fold loading cosine | 0.9851914172 |

The minimum structural held-gene fold has 356 genes. After patient-specific missingness, the
minimum finite held fold has 310 genes and the minimum finite inference set has 1,279 genes.
These are different quantities and are deliberately reported separately.

Every one of the ten cohort leave-pathway-out q05--q95 penalty intervals crosses zero. The
collective dictionary therefore has a modest reconstruction advantage, but the source
evaluation does not establish an individual pathway effect.

## Robust runtime solve

For one caller transition, active evidence contains exact standardized deltas and one-sided
bounds. The coordinate vector \(x\) minimizes

\[
\sum_g r_g\,\rho_{1.345}\!\left(B_gx-y_g\right)
+\frac{1}{2}x^\top\operatorname{diag}(0.25,1,\ldots,1)x,
\]

with ridge \(\lambda=1\). Reliability is

\[
r_g = \frac{\sqrt{q_{g,t}q_{g,t+1}}}
{1+(\mathrm{SE}(\Delta_g)/s_g)^2},
\]

bounded in \((0,1]\). The engine uses deterministic NumPy IRLS, damping 0.7, at most 200
iterations, and coordinate tolerance \(10^{-9}\). It reports an estimate only when the solve
converges, its objective trace is monotone within the locked numerical tolerance, and the
active design condition number is at most 25.

Accepted requests also satisfy the deterministic worst-case work bound

\[
(\lvert T\rvert-1)\left(186+3B\right)\le 4608,
\]

where \(\lvert T\rvert-1\) is the number of consecutive transitions and \(B\) is the
requested bootstrap count. The fixed 186 units conservatively account for the primary solve,
five-by-eleven held-gene reconstruction solves, and all ten pathways' global, processing,
degree, unique-member, and nine possible overlap ablations; each paired bootstrap adds three
solves. This combined gate keeps dense accepted requests inside the 120-second transport
budget while retaining both independent maxima: 16 time points remain available with 32
bootstraps, and 256 bootstraps remain available for up to five time points.

The original 50-iteration prototype left 47 of 520 primary evaluation fits nonconverged and
was rejected. With 200 iterations, all full-patient, global held-gene, joint held-gene, and
5,200 leave-pathway-out evaluation fits converge; the largest observed iteration count is 170.
Nonconverged runtime or bootstrap solves are not silently relabeled as converged.

## Missingness and censoring

- observed to observed produces an exact delta;
- observed to left-censored produces an upper bound;
- left-censored to observed produces a lower bound;
- two left-censored limits are uninformative and excluded;
- missing and unsupported values are excluded and never converted into zero or negative
  observations.

For an upper bound, residual loss is inactive while the prediction remains below the reported
bound. For a lower bound, it is inactive while the prediction remains above the bound. No
latent value is imputed below a censor limit.

## Uncertainty and replay

The artifact contains 256 deterministic patient-cluster source-bootstrap scale/effect draws.
It contains no patient measurements, identifiers, identifier hashes, fold memberships, or
resample indices. Runtime accepts 32--256 draws and defaults to 64.

For each selected draw the engine computes three paired paths:

- measurement-only: perturb reported values or limits, keep the reference fitted model;
- fitted-model-only: keep caller values, use a source-bootstrap scale and design;
- combined: use the paired measurement perturbation and source-bootstrap design.

The result exposes measurement, fitted-model, and combined standard errors; their paired
covariance; and the residual of the variance identity. The 90% interval is the empirical
5th--95th percentile envelope including the point estimate. Seeds and draw selection derive
from a digest of the active numerical request and the fitted content lock, so opaque sample,
time-point, observation, and provenance identifiers do not alter numerical inference.

Exact replay binds the request, profile, fitted bytes/content, source catalog, feature axis,
designs, training recipe, fold policy, evaluation, bootstrap ensemble, input schema, result
validators, engine AST, NumPy 2.5.2, and the synthetic demo semantic oracle.

## Runtime evidence gates

Global output requires at least 16 active genes, 25% coefficient-mass coverage, effective
sample size at least 8, a valid primary solve, and at least 32 valid bootstrap paths.

A numeric pathway coordinate requires at least five active member genes, 50% member-loading
mass coverage, effective sample size at least 3, an estimable global coordinate, and at least
32 valid paired bootstrap paths. Full numerical support additionally requires:

- at least 64 valid bootstrap paths;
- an interval-supported directional or stable class;
- at least 80% bootstrap classification stability;
- at least three active unique members carrying at least 20% of member-loading mass;
- estimable source-processing, degree-normalization, and unique-member ablations without a
  sign reversal;
- all five deterministic caller held-gene folds evaluable, at least four improved by the full
  design, and median relative reconstruction gain of at least 1%; and
- no fixed overlap-confounding flag.

The PI3K/AKT panel event has no unique member and is always reported as overlap-confounded.
Coordinates that pass base estimation but fail any full-support gate remain numeric and
`limited`; they are not discarded or upgraded.

## Packaged fitted artifact

The compact fitted artifact is
`kncc_reactome_conditional_transition_model.v1.json` (4,434,141 bytes). It stores the reference
scale/effect/support tensors, the 1,872 by 11 reference design lock, one ordinary-source-measure
ablation, one no-degree reconstruction derived at load time, 256 float32 bootstrap scale/effect
draws, cross-fitted coordinate MAD scales, and aggregate evaluation evidence.

Loading is fail-closed. The loader checks canonical bytes, byte and content digests, every
tensor byte digest and shape, source-catalog binding, feature union, design reconstruction,
global and conditional loading digests, training constants, fold policy, bootstrap row locks,
evaluation oracles, privacy declarations, and the exact NumPy version. Loaded arrays are
read-only and nested evaluation metadata is recursively immutable.

The reproducible offline importer is
`tools/import_kncc_reactome_conditional_transition_model.py`. It requires the locally admitted,
byte-locked PDC000514 source material and does not access the network.
