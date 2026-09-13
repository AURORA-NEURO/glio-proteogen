# Caller-owned GBM RNA composition runtime

`gbm-rna-composition/0.1.0` is a narrow research runtime around the existing
GBmap Dirichlet--multinomial adaptive-unknown simplex solver. The caller must
provide one complete non-negative count vector, a shared feature axis, and one
strictly positive probability signature per reference lineage. Feature and
reference order are canonicalized before the request digest is calculated, so
equivalent payloads replay identically.

The fit retains an explicit gene-resolved unknown channel rather than
renormalizing known lineages. It returns the converged objective trace, KKT
residual, signature condition number, normalized DM deviance, standardized
Pearson residual, and Aitchison residual. Non-identifiable signatures,
non-finite values, zero-depth counts, or a non-convergent trace produce an
abstained result without a negative composition finding.

Callers may request 8–256 deterministic posterior-predictive perturbations.
Each perturbation samples a Dirichlet composition around the fitted simplex,
draws a multinomial count vector at the observed sequencing depth, and reruns
the same count-native solver with stricter closure tolerances. The request
digest seeds NumPy's generator, accepted draws must have finite monotone
objective traces and bounded KKT residuals, and the result reports 5th/95th
percentile intervals for every ranked lineage plus the unknown channel. The
point estimate is expanded into its interval when necessary so replay receipts
remain coherent. Fewer than eight accepted draws abstain from interval output
rather than manufacturing uncertainty. These intervals represent sampling
uncertainty under the fitted model only; they are not histologic, donor, batch,
or external calibration uncertainty.

This runtime is intentionally caller-owned and source-independent. It does not
open the approximately 9 GB GBmap H5AD, ship a fitted artifact, infer donor or
patient identity, or calibrate a population threshold. The known weights are
RNA mixture weights, not histologic cell fractions or malignant-cell
percentages; unknown mass is never assigned to a lineage. All outputs are
research-use-only and non-prescriptive. The source-admission profile remains
`development_unfitted`, and this runtime does not promote the GBmap candidate
to a source-derived `SUPPORTED` model.

The linked stateless surfaces are:

- `GET /v1/research/gbm-rna-composition/profile`
- `GET /v1/research/gbm-rna-composition/demo`
- `POST /v1/research/gbm-rna-composition/analyze`
- `POST /v1/research/gbm-rna-composition/verify`
- `glio-proteogen gbm-rna-composition profile|demo|analyze|verify`

Requests and results are not persisted. The route is explicitly limited and
caller-owned: it exposes the real solver while the licensed GBmap source and
fitted donor-aware artifact remain admission-gated.
