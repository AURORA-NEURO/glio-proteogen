# Caller-owned glioma immunopeptidomic presentation

`glioma-immunopeptidomic-presentation/0.1.0` is a research-only runtime for
ranking peptide candidates against an explicitly supplied HLA-I model package.
It closes the numerical path that was previously only represented by the M19
contracts, while preserving the redistribution boundary: this checkout does
not ship NetMHCpan, MHCflurry, or any other pretrained binding artifact.

## Model boundary

The caller supplies one digest-bound model per requested HLA allele. Each model
contains position-specific amino-acid log-odds matrices for peptide lengths
8--14, terminal processing coefficients, an intercept, component scales,
temperature, and source/model digests. The runtime rejects forged model
digests, duplicate lengths, malformed alleles, non-finite coefficients, and
unsupported amino acids. The fixed amino-acid axis is
`ACDEFGHIKLMNPQRSTVWY`.

This makes the result reproducible for a licensed local model package without
turning a synthetic coefficient table into a repository-trained claim. The
profile digest binds the NumPy version, dimensions, score family, bootstrap
default, explicit caller-owned execution scope, position-wise log-odds scoring,
and the multi-allele aggregation policy.

## Scoring and evidence conservation

For every peptide/allele pair the runtime sums the position-specific log-odds
entries (a PSSM likelihood-ratio coordinate with a separate matrix per peptide
length) and computes a
terminal-residue processing score. It adds optional standardized expression
evidence and a caller-declared variant contribution, then applies the model
temperature to a logistic presentation coordinate. When multiple alleles
support a peptide, the calibrated marginal probabilities are combined with an
explicit independent allele noisy-OR, representing the probability that at
least one requested allele presents the peptide; duplicate allele identifiers
are rejected before scoring.

Observed expression is perturbed by its standard error during deterministic
request-digest-seeded bootstrap replicates. Left-censored expression is treated
as an upper bound and contributes only a one-sided penalty when the limit is
below the reference baseline. Missing and unsupported expression states are
ignored; they never become negative peptide observations. At least three
informative peptides are required. Missing allele models yield `limited`
support, while fewer than three supported peptides abstain.

Each supported candidate carries its allele-level scores, a nominal 90%
bootstrap interval (or a degenerate interval when zero replicates are
requested), rank, top component drivers, and four component ablations:
binding, terminal processing, expression, and variant sequence. A result is
sealed by request, profile, model, and result digests; replay recomputes the
same result exactly.

## Interpretation ceiling

The probability is a calibrated-model coordinate only. It is not proof of
cell-surface presentation, immunogenicity, T-cell recognition, diagnosis,
prognosis, vaccine suitability, or treatment response. HLA typing, peptide
generation, proteasomal cleavage, TAP transport, tumor purity, and sampling
remain outside the model. A source-admitted pretrained artifact with external
allele coverage and calibration is still required before this lane can make a
source-derived GBM presentation claim or be promoted beyond caller-owned
research use.
