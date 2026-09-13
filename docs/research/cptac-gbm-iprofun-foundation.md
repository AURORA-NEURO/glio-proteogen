# CPTAC GBM cis-dosage foundation

## Status and claim ceiling

This foundation is `source_captured_not_admitted`. The official CPTAC GBM
processed-data and Table S3 workbooks have been integrity checked, but no fitted
cis-dosage artifact is part of a release profile yet. Until a model passes the
gates below, the repository must not describe Table S3 lookup as an iProFun
reimplementation, convert an unreported flag into a biological negative, or
claim individual causal effects.

The intended output is research-only source-cohort association evidence. It is
not a diagnosis, prognosis, treatment recommendation, causal driver call, or
external validation result.

## Exact source locks

The sources are supplementary files for Wang et al., *Cancer Cell* 2021,
[doi:10.1016/j.ccell.2021.01.006](https://doi.org/10.1016/j.ccell.2021.01.006),
downloaded through the article's official PMC supplementary-material links.

| Source | Bytes | SHA-256 | Admission |
|---|---:|---|---|
| `NIHMS1665743-supplement-3.xlsx` (Table S2) | 129,239,538 | `59c33b6140c88c394da50fd7461774233074dda12361df7989fe51b8b8e28a13` | local source only; not vendored |
| `NIHMS1665743-supplement-4.xlsx` (Table S3) | 357,622 | `098b596756a84c4744b934f25dc5b9a1e49f992827e2d1223179dfb4655f08f5` | local source only; not vendored |

Public availability is not treated as redistribution permission. A future
importer must verify these exact bytes and emit only bounded, de-identified
model/evaluation aggregates. It must not copy patient columns, raw rows, or
patient-derived identifiers into source control, logs, receipts, or API output.

`tools/capture_cptac_gbm_supplements.py` now performs that first boundary: it
verifies both files by byte length and SHA-256, checks every sheet name and used
dimension through a bounded ZIP/XML reader, re-verifies both sources immediately
before writing, and emits a canonical 2.4 KiB cell-free receipt. The receipt
explicitly records that no cells, sample headers, patient identifiers, or
identifier-derived digests were emitted.

## Table S2 inventory

The workbook has 16 sheets. The primary analysis matrices are:

- gene-level GISTIC2.0 CNV: 27,217 feature rows and 99 unique cohort columns;
- FPKM-UQ RNA: 45,914 feature rows and 111 unique cohort columns;
- global proteome: 10,998 feature rows and 111 unique cohort columns;
- phosphoproteome: 70,330 peptide/site rows and 112 unique cohort columns;
- acetylome: 12,455 peptide/site rows and 112 unique cohort columns.

The exact header intersection across CNV, RNA, protein, phosphosite, and
acetyl-site matrices contains 96 cohort columns. Pairwise intersections are
content-digested during capture without persisting or printing identifiers.
Table S2 also contains mutation, segment-CNV, structural-variant, circular-RNA,
miRNA, lipidome, metabolome, and small CBTTC validation sheets.

The source README states that protein, phosphosite, and acetyl-site values were
log2 transformed, median-polish normalized, and ComBat batch corrected, with
features retained at at most 90% missingness. RNA is FPKM-UQ with the same
missingness ceiling. Gene-level CNV uses GISTIC2.0 with threshold `0.3`.
Runtime code must bind these preprocessing statements to the source-profile
digest instead of silently assuming raw counts or interchangeable scales.

## Table S3 inventory and semantic hazards

Table S3 contains three source-anchored summary resources:

- 2,260 NMF feature records: 628 protein, 1,380 phosphosite, and 252 RNA;
- 250 ranked miRNA cluster entries representing 229 distinct miRNAs;
- 8,258 gene rows with four binary reported-call fields: CNV-to-RNA,
  CNV-to-protein, methylation-to-protein, and methylation-to-RNA.

The NMF table contains seven exact duplicate groups (18 participating rows; 11
rows beyond the first). An evidence projection may collapse duplicates only
while preserving source multiplicity and the duplicate policy in its digest.

Nineteen gene-label cells were stored as Excel date serials: five NMF `SYMBOL`
cells and fourteen iProFun `gene` cells. They must be quarantined as
`excel_date_serial_unresolved` unless a separately reviewed accession/HGNC
mapping recovers them. Silent date-to-symbol guessing is forbidden.

An iProFun `0` means only that this summary sheet did not report a positive
call. It does not encode eligibility, a tested null, no association, or missing
evidence. Table S3 contains no coefficient, standard error, posterior,
permutation statistic, or eFDR value. It can validate source-summary
concordance, but it cannot train or calibrate a predictor by itself.

## Candidate fitted model

The first admissible candidate is a glioblastoma cis-dosage propagation model,
not a generic weighted score. For each safely mapped gene, training-fold-only
robust regressions will estimate:

1. CNV-to-RNA propagation;
2. CNV and RNA-to-protein propagation;
3. the RNA-mediated and protein-buffered portions of the total association;
4. residual RNA/protein discordance and uncertainty.

The deterministic NumPy implementation should use Huber IRLS with ridge
stabilization, explicit missing-value masks, fold-local centering/scaling,
convergence traces, and request-digest-derived bootstrap seeds. It should emit
`propagated`, `buffered`, `discordant`, or `indeterminate` only when bootstrap
intervals and support gates justify the state. Table S3 flags are a descriptive
full-cohort concordance check and may never select features inside a held-out
evaluation fold.

## Admission gates

A distinct `cptac-gbm-cis-dosage/*` fitted profile may be admitted only after it
has all of the following:

- exact, reviewed gene mappings with unresolved date-coerced labels excluded;
- patient-grouped outer evaluation and fold-local preprocessing/selection;
- independently calculated small-model regression oracles;
- held-out prediction, direction, stability, interval, missingness, and
  unsupported-to-negative tests;
- modality and mediator ablations that distinguish direct CNV association from
  RNA-mediated protein association;
- a separately labeled full-cohort refit after evaluation is locked;
- compatible redistribution terms for any vendored fitted artifact, or a
  digest-verifying user-side build path when those terms remain unclear.

Internal source-cohort performance must remain distinct from CBTTC transport
checks and from external validation. A lookup-only Table S3 service, if added,
must use a different profile identifier and state `fit_status=not_fitted` and
`claim_ceiling=published_supplementary_table_lookup_only`.
