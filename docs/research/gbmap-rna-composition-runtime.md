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

This runtime is intentionally caller-owned and source-independent. It does not
open the approximately 9 GB GBmap H5AD, ship a fitted artifact, infer donor or
patient identity, or calibrate a population threshold. The known weights are
RNA mixture weights, not histologic cell fractions or malignant-cell
percentages; unknown mass is never assigned to a lineage. All outputs are
research-use-only and non-prescriptive. The source-admission profile remains
`development_unfitted`, and this runtime does not promote the GBmap candidate
to a source-derived `SUPPORTED` model.
