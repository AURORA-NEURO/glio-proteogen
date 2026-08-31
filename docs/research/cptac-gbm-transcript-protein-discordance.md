# CPTAC GBM transcript–protein conditional association

`cptac-gbm-transcript-protein-discordance/1.0.0` is a local-build,
research-only lane for gene-level conditional RNA–protein association in the
locked CPTAC glioblastoma discovery cohort. The algorithm identifier retains
the word `discordance`, but the result contract deliberately uses narrower
labels: positive or inverse conditional RNA association, predictive direction
indeterminate, no incremental RNA support, or indeterminate.

No fitted artifact is bundled with the repository. A user must build an
artifact from their own exact source copies before a query can run. The lane
has no HTTP route, accepts no patient measurements at query time, never emits a
patient score, and caps every estimable result at `limited`. It is not a
biological buffering model, a causal mediation analysis, an iProFun
reproduction, a clinical classifier, or a treatment model.

## Scientific question and estimand

For each requested HGNC gene, the fitter asks whether RNA adds held-out
predictive information for the cohort's protein-abundance axis after including
gene-level CNV. In every outer fold it fits:

- full model: `Protein ~ intercept + RNA + CNV`;
- RNA-only comparator: `Protein ~ intercept + RNA`;
- CNV-only comparator: `Protein ~ intercept + CNV`; and
- null comparator: the training-fold median protein value.

The primary conditional coefficient is the RNA coefficient from the full
model, converted back to the source axes before fold aggregation. The model
also reports the full model's held-out R² difference from each single-predictor
comparator. In particular, `delta_r2_vs_cnv_only` measures incremental
held-out prediction after adding RNA to the CNV-only comparator. It is not a
fraction of protein abundance explained by transcription, and the full-model
residual is not “unexplained biology.” Both remain conditional,
cohort-and-pipeline-relative statistics.

The lane does not subtract RNA and protein values. Such a subtraction would be
invalid because the source axes have different upstream preprocessing and
units. An inverse conditional RNA coefficient may reflect correlation
structure, collinearity, tumor composition, missingness, or technical effects;
it is not sufficient evidence of post-transcriptional buffering or repression.

## Exact local sources and GBM scope

The source cohort comes from the CPTAC study reported by Wang et al. The paper
describes integrated molecular profiling of treatment-naive adult GBM, and the
NCI Proteomic Data Commons identifies PDC000204 as the corresponding CPTAC GBM
Discovery Study proteome. This repository uses only the exact Table S2 and
HGNC snapshots below for this lane.

| Source | Bytes | SHA-256 |
| --- | ---: | --- |
| CPTAC GBM Table S2 | 129,239,538 | `59c33b6140c88c394da50fd7461774233074dda12361df7989fe51b8b8e28a13` |
| HGNC approved-symbol snapshot | 16,948,224 | `854162118530e929f06249f3349465dd5fe0515fcccf0347f463e833609c1270` |

The exact parser resolves 96 common measurement columns into 96 patient
groups and a 10,430-gene CNV/RNA/protein universe. A local fit is bounded to
one through 256 genes selected before fitting. That bound is operational; it
does not imply that a 256-gene fitted artifact ships with the repository.

The Table S2 source README describes the relevant inputs as gene-level
GISTIC2.0 CNV, FPKM-UQ RNA, and normalized global proteome. Protein values were
already log2 transformed, median-polish normalized, and ComBat batch corrected;
RNA remains an FPKM-UQ abundance axis. Features in the source were retained
under its missingness rules. The fitter does not reinterpret any of these
values as raw counts, absolute protein copies, or mutually interchangeable
units.

Gene reconciliation is conservative. RNA Ensembl identifiers are mapped after
removing only their version suffix, CNV labels lose only a terminal `|chr...`
suffix, and protein features require exact approved HGNC symbols. Collisions,
aliases, non-text keys, and inferred Excel-date repairs are excluded rather
than guessed.

Table S3 is not a fitting input to this lane. Its iProFun-derived reported-call
fields neither select genes nor set thresholds, labels, or support. A missing
or zero source flag therefore cannot become a negative observation here.

## Five-fold Huber IRLS estimator

The exact source parser assigns deterministic, outcome-blind outer folds. Each
row entering the model represents one already resolved patient group. `NaN` is
the only missing-value marker; a gene is evaluated on jointly finite CNV, RNA,
and protein rows, while infinities are rejected.

Within each fold, every scale and regression coefficient is learned from the
training complete cases only. The shared robust fitter uses median centering,
`1.4826 × MAD` scaling with an SD fallback, Huber IRLS with `k=1.345`, at most
30 iterations, an `1e-8` convergence tolerance, and an `1e-8` slope ridge. All
three fitted model families must be numerically identified and converged before
the fold contributes predictions.

A gene must satisfy all of these gates:

- at least 48 complete training patient groups and 3 complete held-out patient
  groups per accepted fold;
- at least 4 accepted folds out of 5;
- at least 60 aggregate out-of-fold observations; and
- finite aggregate metrics and conditional RNA slopes.

The full, RNA-only, CNV-only, and training-median metrics are calculated on the
same accepted out-of-fold support. Stored aggregate metrics are tie-aware
Spearman correlation, R² against the corresponding fold's training-median
prediction, mean absolute error, and `1.4826 × MAD` of full-model residuals.
The fold-level conditional RNA slopes are summarized by their median, scaled
MAD, and the fraction whose nonzero sign agrees with the fold median.

Exact out-of-fold observations, predictions, and residuals exist only as
immutable, non-pickleable development arrays during fitting. They are excluded
from the local artifact and every query or replay result.

## Deterministic patient bootstrap

The default uncertainty procedure runs 128 deterministic patient-bootstrap
replicates. Within each replicate, patient groups are sampled with replacement
inside each of the five existing fold strata, and the entire five-fold fitting
and evaluation procedure is repeated. The seed is derived from a SHA-256 digest
that binds the profile, exact source locks, and gene symbol; patient identifiers
do not seed the procedure and are not retained.

A gene abstains if fewer than 80% of requested replicates succeed. Under the
locked 128-replicate profile, at least 103 complete refits are required.
Successful replicates produce interpolation-free, nearest-rank nominal 90%
intervals for:

- full-model R²;
- delta R² versus the RNA-only comparator;
- delta R² versus the CNV-only comparator;
- full-model mean absolute error;
- full-model residual MAD; and
- the median conditional RNA slope.

Point summaries and interval bounds are quantized to eight decimal places for
stable receipts. These intervals describe sampling variability inside this
source cohort. They are not calibrated patient-prediction intervals or
external-validation intervals.

## Pattern rules, support, and abstention

Every gene with an accepted fit receives `limited` support; no result can be
promoted to `supported`. The pattern rules use the nominal 90% bootstrap
intervals and the prespecified 0.80 fold-sign-stability floor:

- `positive_conditional_rna_association`: the lower interval bound for delta R²
  versus CNV-only is above zero, fold-sign stability is at least 0.80, and the
  conditional RNA-slope interval is wholly above zero;
- `inverse_conditional_rna_association`: the same incremental-prediction and
  stability gates pass, and the slope interval is wholly below zero;
- `predictive_direction_indeterminate`: the lower bounds for delta R² versus
  CNV-only and full-model R² are above zero, but the conditional direction is
  not both stable and interval-supported;
- `no_incremental_rna_support`: the upper interval bound for delta R² versus
  CNV-only is at or below zero; and
- `indeterminate`: the intervals cross one or more remaining zero boundaries.

`no_incremental_rna_support` is not evidence that RNA has no biological role.
Likewise, the positive and inverse labels are statistical conditional
associations, not mechanisms. The reported delta R² versus RNA-only is an
additional ablation result and does not change these labels.

A requested gene abstains when it was predeclared but no stored fit cleared the
fold, OOF, convergence, and bootstrap gates. The artifact also retains the
sorted predeclared gene set, so a later query for a gene that was never fitted
is reported honestly as “no computation was attempted” rather than as a model
failure. Abstention withholds statistics; missing or unsupported evidence is
never converted into a negative result.

The zero-boundary classification is repository policy. This lane performs no
genome-wide multiplicity calibration, permutation testing, or independent
validation, so the nominal 90% intervals must not be read as discovery
significance. These limitations are why `limited` is the maximum support.

## Local artifact workflow

The registered local CLI group is:

```text
glio-proteogen cptac-gbm-transcript-protein-discordance <command>

commands:
  profile
  fit-local ...
  analyze REQUEST.json --artifact ARTIFACT.json
  verify RECEIPT.json --artifact ARTIFACT.json
```

`fit-local` requires `--table-s2`, `--hgnc`, and a new `--output` path. The
repeatable `--gene` option supplies one through 256 predeclared gene symbols,
for example `--gene EGFR --gene PTEN`. The command copies each input into a
private operating-system temporary directory while checking the exact byte
count and SHA-256 in the same bounded streaming pass. Only the staged,
read-only snapshot is parsed. The temporary copies are removed on ordinary
success and failure; an abnormal process or host termination can still leave
private crash residue, so routine host temporary-file cleanup remains
necessary.

The fitter writes a canonical JSON artifact of at most 32 MiB. Publication uses
an fsynced same-directory temporary file and an exclusive hard-link create, so
an existing destination is never overwritten. The artifact stores only the
sorted predeclared gene set, successful gene-level aggregate metrics,
uncertainty, fold counts, exact source locks, cohort invariants, the
algorithm-profile digest, and a canonical content digest. It explicitly
contains no measurement vectors, sample headers, patient identifiers or
identifier-derived hashes, fold membership, OOF predictions, or residual
arrays.

The production query gate requires:

- `derivation_status=locally_verified_exact_sources`;
- the exact two source locks and the 96/96/10,430 cohort invariants;
- NumPy 2.5.2 and the matching content-bound profile digest, whose engine
  semantic digest also binds the shared Huber solver, exact OOXML cohort
  parser, inherited source/contract semantics, local CLI adapter, central CLI
  registration, and absence of a central HTTP binding; and
- 128 requested bootstrap replicates for every fitted gene entry.

Synthetic development artifacts fail this gate. A query contains only an
opaque query ID, the artifact content digest, and one through 256 exact gene
symbols. It never contains new patient values. Request, result, and replay
payloads are bounded to 64 KiB, 4 MiB, and 8 MiB respectively.

`analyze` returns a content-addressed result receipt. `verify` reloads the same
local artifact, recomputes the result, and checks request, profile, artifact,
result-digest, and semantic equality. These checks protect deterministic replay
and accidental corruption inside a same-user local trust boundary. They do not
prove authorship: cross-user distribution would require a signed manifest, a
separately trusted verification key, and admitted redistribution terms.

No public HTTP adapter is mounted. The local artifact and every derived output
remain `redistribution_status=local_only_terms_unverified` and must not be
served from a shared deployment while those terms remain unresolved.

## Relationship to iProFun and governed M08

The source GBM paper used iProFun to evaluate associations from DNA-level
alterations to molecular quantitative traits. The published iProFun method
models DNA alteration associations with RNA, protein, and phosphoprotein traits
and integrates that evidence across trait types. It does not define this
repository's cross-fitted `Protein ~ RNA + CNV` model.

Accordingly, this lane does not import iProFun posterior thresholds, false
discovery calls, or biological-direction filters. It omits the full age, sex,
purity, recurrent-mutation, and other alteration adjustment used in the source
analysis. Its output must never be described as an iProFun result or
reproduction.

The implementation is additive under `glio_proteogen.research`. It does not
modify, redirect, or promote any governed M08 v1 contract, route, schema digest,
or provisional engine. A future M08 research facade would require a separate
reviewed integration and cannot broaden this lane into patient-level inference.

## Primary sources

- Wang et al., “Proteogenomic and metabolomic characterization of human
  glioblastoma,” *Cancer Cell* 39 (2021), 509–528.e20,
  [doi:10.1016/j.ccell.2021.01.006](https://doi.org/10.1016/j.ccell.2021.01.006)
  and [PMC8044053](https://pmc.ncbi.nlm.nih.gov/articles/PMC8044053/).
- [Official Wang et al. Table S2 workbook](https://pmc.ncbi.nlm.nih.gov/articles/instance/8044053/bin/NIHMS1665743-supplement-3.xlsx),
  the exact local source snapshot accepted by this fitter.
- [NCI Proteomic Data Commons study PDC000204](https://pdc.cancer.gov/pdc/study/PDC000204),
  “CPTAC GBM Discovery Study - Proteome.”
- Song et al., “Insights into Impact of DNA Copy Number Alteration and
  Methylation on the Proteogenomic Landscape of Human Ovarian Cancer via a
  Multi-omics Integrative Analysis,” *Molecular & Cellular Proteomics* 18
  (2019), S52–S65,
  [doi:10.1074/mcp.RA118.001220](https://doi.org/10.1074/mcp.RA118.001220)
  and [PMC6692782](https://pmc.ncbi.nlm.nih.gov/articles/PMC6692782/).
