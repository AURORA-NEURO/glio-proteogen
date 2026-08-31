# KNCC/Neftel bulk-protein program transitions

## Scope

`kncc-neftel-program-transition/1.0.0` is a research-only, stateless model for
ordered bulk-protein measurements on the PDC000514 assay scale. It estimates one
global primary-to-recurrent source-cohort concordance coordinate and eight
Neftel marker-set coordinates conditional on that global axis.

The eight coordinates are **not** single-cell states, cell fractions, clinical
subtypes, patient trajectories, recurrence predictions, pathway activities,
prognoses, or treatment evidence. The fitted dictionary improves held-marker
reconstruction over a global-only axis but does not outperform the prespecified
equal-membership Neftel baseline. Consequently every estimable program output is
hard-capped at `limited`. The same lane-wide evidence ceiling also caps the
global coordinate because the source-cohort fit has no independent external
validation; the runtime cannot promote any coordinate to `supported`.

## Exact source bindings

The offline fitter consumes the exact PDC000514 protein files already admitted
by the longitudinal GBM source lock and the exact Neftel Table S2 marker catalog
already admitted by the Neftel research lane.

- PDC study: `PDC000514`, version UUID
  `524d5116-b6de-4e36-892a-e35dba7d0170`.
- Cohort: 104 strict patient-grouped primary/recurrent pairs and 11,312 mapped
  protein features.
- Primary protein measure: `Unshared Log`; the ordinary `Log` measure is kept
  only as an explicit source-processing ablation.
- PDC source-binding digest:
  `sha256:7e02e4366b7fe063b768fb29109b33e4ec673fa23d0cb4ac2f307cce8dada9d1`.
- Neftel marker-catalog content digest:
  `sha256:5f0baa349db65f0ee740a318db6aad334b4ab9fa94b9f9d69158441054c1582f`.
- Exact fitted program-membership digest:
  `sha256:193f2be224e655a4a5522e73ef01f965a76abb449b6af6ef77d67a36a10c195c`.
- Source articles: [Kim et al., 2024](https://doi.org/10.1016/j.ccell.2023.12.015)
  and [Neftel et al., 2019](https://doi.org/10.1016/j.cell.2019.06.024).

The repository records PDC000514 article/data terms as CC BY 4.0. It does not
invent or assert separate licensing terms for the Neftel workbook; its citation,
source bytes, transformation, and catalog digests remain distinct.

| Program | Source markers | KNCC mapped | Fitted eligible |
| --- | ---: | ---: | ---: |
| MES2 | 50 | 42 | 40 |
| MES1 | 50 | 49 | 47 |
| AC | 39 | 37 | 36 |
| OPC | 50 | 47 | 46 |
| NPC1 | 50 | 43 | 42 |
| NPC2 | 50 | 41 | 38 |
| G1/S | 29 | 26 | 14 |
| G2/M | 45 | 37 | 25 |

The mapped union contains 289 genes before reference-fit eligibility is applied;
the fitted union contains 256 unique genes. A marker shared by multiple programs
is weighted by the inverse square root of its membership degree.

## Fitted algorithm

All fitting is offline and patient-grouped. For each training fold, the fitter
recomputes Huber locations, MAD scales, coverage eligibility, a global source
loading, and eight program loadings. Each program loading begins with the
training-only standardized PDC000514 source effect within the exact Neftel mask,
then is degree-corrected, normalized, and orthogonally residualized against the
global loading.

Coordinates minimize a robust joint objective with deterministic damped Huber
IRLS coordinate descent and ridge penalties. The global coordinate uses a lower
ridge multiplier than the conditional coordinates. Runtime left-censored values
remain one-sided bounds; missing and unsupported values are excluded and never
become zero or negative observations. A censor bound contributes to reported
coverage and effective sample size only when its standardized one-sided residual
is loss-bearing beyond the locked `1e-8` tolerance at the converged solution.
Receipts separately report all reliable admitted bounds and the smaller set of
informative binding bounds. Estimation additionally requires at least 16 exact
observed-to-observed deltas globally and five exact deltas for each program, so
loose censor limits cannot manufacture directional or neutral support.

The fitted artifact contains 128 deterministic patient-bootstrap refits. At
runtime, request-digest-derived streams separately perturb measurements, select
source-bootstrap coefficients, and combine both effects. Requests above 128
replicates use deterministic balanced rounds over that fixed 128-refit ensemble;
each round has an independent measurement-perturbation stream, and the runtime
reports the exact requested count rather than silently capping it. These repeated
source rows do not represent additional unique patient refits. Results report the two
standard errors, their covariance, combined standard error, interval, and
variance-closure residual. Structural explanations include source-processing,
degree-normalization, unique-member, leave-program-out, overlapping-program, and
top-contribution checks. Each reported top-contribution check is a real
omit-one-measurement robust refit, warm-started from the converged joint solution.
Removing a program's own coordinate does not define a replacement coordinate,
so `leave_program_out` explicitly abstains instead of returning a tautological
zero; the separately typed five-fold held-marker reconstruction gain reports the
actual omitted-program predictive comparison. Every receipt is quantized and
exactly replayable.

## Locked evaluation and release gate

Evaluation uses eight deterministic held-patient folds. Every source statistic
and loading is refit on the training patients. Within each held patient, five
deterministic held-marker folds test reconstruction from the remaining markers,
for 520 aggregate patient/fold evaluations. The patient-cluster intervals use
20,000 deterministic patient resamples.

| Model | Median standardized MAE |
| --- | ---: |
| Zero prediction | 0.7246259767 |
| Global only | 0.6039095267 |
| Equal-membership Neftel | **0.5177467313** |
| Fitted global + conditional dictionary | 0.5754778047 |

- Fitted versus global-only median relative MAE gain: `+0.0261168032`.
- Patient-cluster fitted-versus-global median gain: `+0.0248465156`, nominal
  90% interval `[0.0153265550, 0.0380342956]`.
- Fitted versus equal-membership median relative MAE gain: `-0.1056177130`.
- Patient-cluster fitted-versus-equal median gain: `-0.0987176386`, nominal 90%
  interval `[-0.1155036986, -0.0777444485]`.
- All eight leave-program-out 5th–95th percentile intervals cross zero.
- All fitted and evaluation solver roles converged. The reference design
  condition number is `9.0087204802`; the minimum held-fold loading cosine is
  `0.9763235009`.

These results trigger the locked release gate
`limited_fitted_dictionary_not_preferred_to_equal_membership`. The model remains
valuable as a transparent conditional-coordinate experiment and negative
result; it is not evidence that the fitted program weights are preferable to
the simpler Neftel marker baseline.

## Artifact, privacy, and replay

The shipped aggregate artifact is
`src/glio_proteogen/research/longitudinal_gbm_neftel_transition/data/kncc_neftel_program_transition_model.v1.json`.

- Bytes: `357871`.
- Raw SHA-256:
  `sha256:920f66efa326e6b2d1b92f12dbc055c590e5774be1af09c82a03ca24cdba01eb`.
- Canonical content digest:
  `sha256:7f535d98a5c6da796617fdc5ae1f95a41843eb7285660fe61ee12a1f24a9aea2`.
- Evaluation digest:
  `sha256:14a773347547306420d288620b3344f18b1f1100cc97bb5ab12e0c3f4b19ccad`.
- Bootstrap-ensemble digest:
  `sha256:cea991982fb0e23aa87193cc0c76384908024549c5bf12c2e041cf8d41a697de`.
- Runtime profile digest:
  `sha256:b9f624e7b4fb64edd3cf0d4558727ddc0fd93d5f033d55d4d0af6805dafcdd53`.
- Synthetic demo request/result digests:
  `sha256:8f83b633902fe36fb8daf93c0a6add1202a64ade776e287f8190e87edaea7da0`
  and `sha256:2bb1627cc8b9c02bc4c5225f1f1c1264b06bc20e73cb73f665d28947c9af4788`.

No patient measurement, identifier, identifier hash, score, residual, fold
assignment, or bootstrap resample index is serialized. The runtime accepts only
caller-owned observations and never persists requests or results.

The public prefix is
`/v1/research/longitudinal-gbm-neftel-transition`, with `profile`, `demo`,
`analyze`, and `verify` operations. The matching CLI group is
`glio-proteogen longitudinal-gbm-neftel-transition`. HTTP requests are capped at
2 MiB, results at 4 MiB, replay envelopes at 8 MiB, two concurrent analyses per
process, and a 120-second whole-request deadline.

The exact artifact can be rebuilt from locally held digest-matching sources:

```bash
uv run python tools/import_kncc_neftel_program_transition_model.py \
  --pdc-source-dir /path/to/PDC000514/source-lock \
  --hgnc-source /path/to/hgnc_complete_set.txt
```

Raw PDC and HGNC source files are intentionally not distributed inside the
package.
