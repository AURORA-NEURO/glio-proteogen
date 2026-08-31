# GBM master-kinase signature concordance

`sphinks-gbm-master-kinase-concordance/1.0.0` is a synchronous,
stateless research model for comparing a caller-supplied standardized
phosphosite contrast with the subtype-specific master-kinase signatures
reported by Migliozzi et al. It emits independently calculated evidence
concordance, uncertainty, competitive rank enrichment, false-discovery
adjustment, and ablations. It does not emit calibrated kinase activity,
subtype probability, causality, diagnosis, prognosis, or treatment advice.

This implementation is not a port or retraining of SPHINKS/MK. The public
MAKINA repository does not contain the fitted SVM ensemble, training negatives,
complete bagging state, locked package environment, or seeded training run
needed for an exact runtime reproduction. GLIO-PROTEOGEN therefore uses a
separately identified estimator over the paper's published, CC-BY-4.0
supplementary signatures and describes its output as signature concordance.

## Frozen source catalog

The reproducible importer reads Supplementary Tables 5a, 5d, and 5e from the
paper's 7,635,280-byte workbook. It verifies the workbook before parsing and
emits canonical JSON. `--source` accepts the exact workbook and
`--source-archive` accepts a bounded supplementary archive containing exactly
one safe member with the expected basename. Automatic direct and mirror
retrieval is bounded, retried, and best-effort because those transports can be
temporarily unavailable; the exact workbook size and SHA-256 remain the
authority in every mode.

- Article: *Integrative multi-omics networks identify PKCδ and DNA-PK as
  master kinases of glioblastoma subtypes and guide targeted cancer therapy*,
  Nature Cancer 2023, DOI `10.1038/s43018-022-00510-x`, PMCID `PMC9970878`.
- Attribution: © The Authors 2023. Article and supplementary workbook licensed
  under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- Workbook SHA-256:
  `865a2db1ec99dcf047d6ff56b313a21607b840e5239bb9184739f6f6f217fb88`.
- Table 5a: 34,098 unique `(source site label, RefSeq, peptide)` tuples and
  30,175 unique exact source site labels. Ambiguous labels remain ambiguous;
  the importer never invents an isoform assignment.
- Table 5d: 3,560 source rows, consisting of 1,256 GPM, 34 MTC, 467 NEU, and
  1,803 PPR rows. There are 225 extra repeated kinase-site rows. Source row
  identity is retained, while inference collapses each kinase-site group once.
- Table 5e: 24 master kinases, consisting of 9 GPM, 1 MTC, 7 NEU, and 7 PPR
  references. Paper labels are retained and mapped through a closed,
  digest-bound 24-entry HGNC table.

The profile binds the canonical catalog bytes and content, each table
projection, label mapping, synthetic demo request, a locked projection of the
demo's scientific point result, normalized computational-source text, NumPy
`2.5.2`, estimator constants, support gates, tolerances, random-seed policy,
and output quantization. Source text is decoded as UTF-8 and CRLF/CR line
endings are normalized to LF before stable, ordered path-labelled hashing, so
the digest is identical in Git checkouts and wheels on different platforms.
The location solver is capped at 32 deterministic bisection iterations, and a
profile-bound 14,000,000-unit admission budget bounds bootstrap and permutation
work before execution. The current profile digest is
`sha256:bbd25777ede1c62d1cd662cae55be2fb3f2f0bfb6680eb68dbe84a22ebb5e964`.

`known_phosphosite_plus_substrate` and the source Spearman coefficient are
retained in the source catalog for auditability. The former may reflect
third-party PhosphoSitePlus curation and is preserved only as source-reported
metadata; it is not redistributed as an independent PhosphoSitePlus dataset.
Neither field is silently granted extra computational weight. The source SVM
probability is the only published edge weight used by this estimator.

## Input semantics

The request contains an opaque sample identifier, an explicit numerator and
denominator for a caller-supplied standardized log2 contrast, and up to 4,096
phosphosite observations. An active observation must use an exact Table 5a
source label and provide an effect, positive standard error, positive quality
weight, and provenance digest. Fake active labels are rejected before
inference.

Evidence state is typed:

- `observed` is a point observation;
- `left_censored` is an upper detection limit, whose supplied standard error
  represents uncertainty in that reported limit, and receives one-sided loss;
- `missing` and `unsupported` carry no numeric value, require zero quality, and
  never enter the objective or rank background.

Observation and phosphosite identifiers must be unique. JSON duplicate keys,
non-finite values, malformed contracts, and oversized bodies are rejected by
the adapter without echoing submitted content.

## Estimators

For kinase \(k\) and phosphosite \(i\), repeated Table 5d rows are collapsed to
one site with mean source SVM probability \(s_{ki}\). Its reliability is

\[
w_{ki}=\frac{s_{ki}q_i}{\sigma_i^2+0.25^2},
\]

where \(q_i\) is caller quality and \(\sigma_i\) is the supplied standard
error. The location estimate minimizes a ridge-regularized Huber objective. An
observed value contributes a two-sided residual. A left-censored upper limit
contributes only when the proposed location exceeds that limit. The monotone
Huber gradient is solved by deterministic bisection, not by a weighted-average
shortcut.

The independent rank method ranks observed effects within exact residue strata
(`S`, `T`, `Y`, and their multi-site combinations), maps average tied ranks to
`[-1,+1]`, and computes a reliability-weighted signature score. It requires at
least three mapped signature sites, twenty observed background sites, and three
non-signature competitors in every represented residue stratum. Its conditional
random-set null keeps each source signature's SVM edge weights fixed and draws
same-sized observed `(percentile rank, standard error, quality)` tuples without
replacement within residue strata. Rank and measurement precision therefore
move together, rather than reusing a selected signature site's precision after
its rank is replaced. Two-sided empirical p-values use the plus-one correction;
Benjamini-Hochberg q-values use the fixed family of all 24 predeclared master
kinases, assigning an untested member a null p-value of one rather than shrinking
the family after seeing support.

Measurement uncertainty comes from 64 perturbation replicates by default and
up to 256 on request. Point observations receive normal perturbations at the
caller-supplied fixed standard error. A censored observation's reported upper
limit receives a symmetric normal perturbation at the declared limit-uncertainty
standard deviation and remains censored; it is not first tightened and then
re-censored. Each global bootstrap replicate retains its identity as either a
finite estimate or an explicit failure. Intervals and subtype pooling require
at least the profile-bound 80% successful-replicate fraction. A method with
80--99% success is downgraded to `limited`; below 80% it abstains and exposes
requested, successful, and used replicate counts. Subtype summaries use only
same-index complete replicate tracks, preventing results from unrelated draws
from being combined. The 5th and 95th percentiles form a nominal 90% interval
that is widened to include the point estimate. This interval reflects only the
declared fixed-error/limit-uncertainty perturbation model; it does not estimate
covariance, between-sample biological variance, or source-signature uncertainty.

Per-kinase output includes location and rank estimates, p/q-values, effective
sample size, exact support and bootstrap counts, coverage, method agreement,
discordance, bootstrap direction stability, top phosphosite drivers,
residue-family ablations, source references, and abstention reasons. Every
driver names the exact request observation and its provenance digest, in
addition to the contributing Table 5d row identities. Result provenance is
self-contained: it carries the article DOI, title, authors, URL, license and
license URL, transformation notice, engine-source digest, and demo-result
oracle digest. Repeated source rows stay visible in driver provenance but never
multiply support, ESS, the objective, permutations, or bootstrap samples.

The four subtype summaries robustly pool only estimable member-kinase locations,
weighted by the published source MWW score and local effective sample size.
They include leave-one-kinase-out ablations. They are continuous aggregate
signature evidence, not a classifier or probability; the one-member MTC summary
is explicitly limited.

Classification uses the entire interval:

- `activated` only when the lower bound is above `+0.25`;
- `suppressed` only when the upper bound is below `-0.25`;
- `neutral` only when the interval lies wholly inside `[-0.25,+0.25]`;
- otherwise `indeterminate`; and
- `not_estimable` when the location method abstains.

## Replay and interfaces

The computational random seeds derive from a canonical, profile-bound request
digest. Observation order and non-computational identifiers cannot perturb the
numerical draw stream. Results are quantized to six decimals, content-addressed,
and never persisted server-side. Replay recomputes the request and compares the
profile, request digest, result digest, and complete semantic payload. A source
or semantic-oracle change necessarily changes the profile digest, so draft
receipts produced before this pre-release correction are intentionally not
replay-compatible.

HTTP operations:

- `GET /v1/research/gbm-master-kinases/profile`
- `GET /v1/research/gbm-master-kinases/demo`
- `POST /v1/research/gbm-master-kinases/analyze`
- `POST /v1/research/gbm-master-kinases/verify`

Matching CLI commands are available under `glio-proteogen
gbm-master-kinases profile|demo|analyze|verify`. Analysis requests and results
are capped at 2 MiB; replay envelopes are capped at 4 MiB. The HTTP adapter
admits two concurrent computations per process and applies cancellation,
disconnect, and deadline checkpoints.

The versioned synthetic demo uses only real pinned topology labels with
synthetic effects. Its locked directions are activated GPM, activated NEU,
activated PPR, and suppressed MTC/PHKG2. It contains no patient data and is an
algorithm oracle, not biological validation.

Bounded deterministic simulations provide numerical regression checks, not
external biological validation. Across 200 locked Gaussian experiments the
nominal 90% location interval covered its generating value in 90% of cases.
Across 200 heteroscedastic global-null experiments with 24 five-site signatures
and 256 permutations, the probability of any fixed-family BH discovery at
`q <= 0.10` was 0.07 (conservative relative to the 0.10 upper target). The
published signatures and master-kinase labels were selected in the source GBM
cohort; concordance to them in a new request is therefore neither independent
validation of their discovery nor evidence of clinical utility.
