# CPTAC GBM source-defined feature space

Profile `cptac-gbm-source-defined-feature-space/1.0.0` expands exact assay
admission beyond the frozen sixteen-gene panel. It asks which discovery-source
protein identities have interpretable RNA/CNV projections and enough observed
source measurements for later, separately specified analyses. It reports
identity, missingness, count capacity and simple training-variation diagnostics.
It performs no association tests, model fits, prediction scoring, gene ranking
or biomarker selection.

Freeze this specification, implementation, source bindings and synthetic tests
before the first feature-space measurement run. The existing discovery and
confirmatory candidate plans contain 72 and 56 case groups, respectively; these
are fixed input inventories, not new cohort-wide clinical claims. No expanded
feature inventory or empirical coverage result is asserted by this document.
All original panel admission, Table S2 fitting, provider-transfer and sensitivity
profiles, thresholds and artifacts remain unchanged.

## Sources and identity axis

Use the existing exact-byte-bound PDC000204 discovery protein assembly and
official channel map, the paired discovery GDC STAR/AscatNGS files, and the
locked approved HGNC snapshot. The frozen source plan owns case/specimen/file
attribution and candidate order; content hashes verify local integrity, not
issuer authenticity, genetic donor identity or clinical eligibility.

Define the feature axis as the union of all approved HGNC identities admitted
from discovery protein rows and all sixteen existing panel anchors:

```text
CDK4 CDKN2A CDKN2B EGFR IDH1 MDM2 MDM4 NF1
PDGFRA PIK3CA PIK3R1 PLCG1 PTEN PTPN11 RB1 TP53
```

Deduplicate by exact HGNC ID and sort HGNC ID strings lexicographically. Use
that one order for every matrix, state array and result row. Anchors remain on
the axis even when no corresponding protein row exists. Unresolved protein
rows contribute aggregate exclusion counts; never guess an approved identity
from a symbol, description, alias or measurement pattern. Preserve the existing
checks against colliding HGNC/NCBI identities and conflicting approved symbols.
An approved identity without a usable Ensembl cross-reference stays visible
with unavailable projection states rather than disappearing from the axis.

HGNC IDs remain stable when symbols change; the snapshot and its cross-reference
ambiguities are part of the method, not a live online remapping operation.
[HGNC primary resource description](https://pmc.ncbi.nlm.nih.gov/articles/PMC9825485/)

Project each RNA/CNV row only through an exact approved HGNC identity with a
unique matching Ensembl reference and an agreeing approved symbol. Remove only
the supported numeric Ensembl version suffix; preserve `_PAR_Y`. Duplicate
exact or normalized source IDs, contradictory stable identities and malformed
files fail closed. Never average duplicates, merge PAR-Y with its unsuffixed
counterpart or rescue disagreement by an alias search. Missing and ambiguous
cross-references remain explicit.

## Measurement and availability semantics

Keep the existing provider coordinates:

| Axis | Selected value | Preserved distinction |
| --- | --- | --- |
| Protein | CDAP unshared median-normalized log2 specimen/reference ratio | All-peptide ratios never fill unshared blanks; these are relative coordinates, not absolute abundance. |
| RNA | STAR `fpkm_uq_unstranded` under the declared GENCODE v36 schema | Raw counts, TPM, FPKM and FPKM-UQ are different coordinates. |
| CNV | AscatNGS integer total `copy_number` | This is neither GISTIC nor a log2 segment mean. |

PDC documents the reference-ratio and unshared-peptide distinction.
[PDC quantitation documentation](https://pdc-docs.cancer.gov/pdc/explore-quantitation-data)
GDC documents the RNA coordinates and the empty gene-level CNV value when no
segment overlaps a gene. Those documentation facts do not establish identical
historical processing or CNV annotation releases for the selected files.
[GDC RNA pipeline](https://docs.gdc.cancer.gov/Data/Bioinformatics_Pipelines/Expression_mRNA_Pipeline/),
[GDC CNV pipeline](https://docs.gdc.cancer.gov/Data/Bioinformatics_Pipelines/CNV_Pipeline/)

For each gene/case/axis use exactly one state:
`observed`, `absent_feature`, `unresolved_reference`, `ambiguous_identity`,
`symbol_disagreement`, or `missing_measurement`. Only `observed` supplies a
finite value. A finite zero is observed; a structurally absent protein row and
a blank cell in an existing row are different states. Do not impute, transform,
renormalize, batch-correct or use a different peptide coordinate as fallback.
An absent cross-reference is not evidence that the assay measured biological
zero. An unavailable measurement does not establish a mechanism of missingness.

Proteomics imputation can change downstream conclusions and does not
automatically preserve uncertainty; choosing an imputation method would
require its own method and validation policy.
[Primary imputation benchmark](https://pubmed.ncbi.nlm.nih.gov/37861703/)

## Source catalog before external projection

Read verified source inputs and build the source-defined axis and source
catalog first. Persist its exact identities, source-only aggregate diagnostics
and canonical digest **before any external measurement values are read**.
The execution protocol binds source locks, metadata plans, HGNC, fold rule,
method sources and this document. A receipt records completion of that source
freeze before external projection starts.

Project confirmatory protein/RNA/CNV onto the frozen source axis only. Count
additional external protein identities in aggregate; they cannot expand or
reorder the axis. External completeness, variation, correlations or performance
cannot determine source inclusion or thresholds. All sixteen anchors retain
their prior coverage/projection semantics. The source catalog and final report
must identify the same frozen feature-axis digest.

Prior panel/provider-transfer outcomes were already inspected during platform
development. Source-only admission here prevents a new external-data selection
path; it does not make this a previously untouched cohort or a prospective
biological validation study.

## Counts and training-variation diagnostics

For each cohort and feature report observed counts and finite-zero counts on
all three axes; RNA/protein and CNV/protein pair counts; and the three-assay
joint-complete count. Report every one of the eight binary missingness patterns
in `(CNV, RNA, protein)` order and all six states for each axis, including zero
counts. Patterns sum to the cohort candidate count; axis states partition the
same candidate count. Pair and joint counts must agree with those patterns.
Protein structural presence is reported separately from measured-cell coverage.

Use the original deterministic five source patient folds: SHA256 of exact
source case-key UTF-8 bytes, sorted by digest with case-key tie break, then
round-robin modulo five. Do not use measurements or external identities to
assign folds. No resampling occurs in this profile; candidate counts refer to
the frozen case groups asserted by the plan.

Let `J` be a gene's source joint-complete cases and `n_f` its count in fold
`f`. The source count-capacity flag requires all of:

```text
|J| >= 60
n_f >= 3                                  for every f in {0,...,4}
|J| - n_f >= 48                           for every f
|J| - n_f - n_g >= 32                     for all 20 ordered f != g
```

These are prespecified engineering count checks. They do not establish a
converged fit, numerical rank, estimator validity, statistical power or
population representativeness. They neither replace the legacy four-valid-fold
fit requirement nor assert that even one valid fitted fold exists. A failing
feature remains in the catalog with its counts and failure flags.

Separately evaluate 26 source contexts: the full joint-complete source, five
outer-training subsets excluding one fold, and twenty ordered inner-training
subsets excluding distinct outer/inner folds. For each assay axis report the
number of contexts containing at least two distinct finite values on that
context's joint-complete cases, together with the fixed denominator 26. Empty
or singleton contexts do not qualify. Distinctness uses numeric equality;
zero is a value and positive/negative zero are the same value. Report counts,
not individual values, training memberships or fitted coefficients.

Two distinct values do not prove full-design rank, acceptable conditioning,
residual RNA variation after CNV adjustment or solver convergence. These
variation diagnostics do **not** gate the feature axis or source count-capacity
catalog. A constant CNV coordinate does not erase otherwise observed RNA or
protein measurements, and no reduced model is silently substituted.

For the external cohort, `joint_complete >= 48` is a descriptive count flag.
The external cohort is not required to satisfy source OOF/training counts.
This flag does not admit a legacy fit, a transfer benchmark or independent
validation; those operations need separately specified numerical and scientific
requirements.

## Scale, privacy and release gates

`build_source_catalog(matrix, folds)` returns a `SourceFeatureCatalog` with
per-feature coverage, count capacity and training-variation diagnostics and a
canonical aggregate digest. `project_external_coverage(source, matrix)` checks
the frozen identity axis before returning external aggregate coverage.
`FeatureMatrix.gene(hgnc_id)` returns transient aligned `GeneMeasurements`
usable by an existing fitter in a separate experiment; this profile never
calls that fitter or inherits its admission merely by exposing the inputs.

Bound exact feature and candidate dimensions by `MAX_FEATURES = 20000` and
`MAX_CASES = 1000`, and each gene-by-case matrix by `MAX_CELLS = 2000000`.
Validate dimension products before allocation. Use dense float64 arrays with
bytes-backed immutable storage; state arrays must agree with finite-value
availability. Keep private measurements hidden from representations and reject
pickling/serialization. Parse each verified assay file once per cohort and
project onto its already fixed identity axis; no persistent patient-value
cache or individual matrix export is introduced.

The public result contains gene identities and aggregate counts/diagnostics,
source/protocol digests and limitations. It contains no patient/specimen/file
identifiers, individual measurement vectors, predictions, residuals, fold
memberships or bootstrap draws. Actual source-derived catalogs and outputs
remain `local_only_terms_unverified`; they are not committed or uploaded.

Release requires synthetic identity/state/zero/conservation and boundary
oracles; fixed-axis external-exclusion and source-freeze ordering tests;
immutable/private array tests; and exact preservation of the old panel
projections. After source freeze, run two complete local evaluations and
verify byte-identical aggregate packets. Independently compare raw-source
projections and aggregate accounting and review statistical scope and privacy.
No complete expanded feature list or real eligibility result is claimed until
that run and review finish.

## Scientific boundary and follow-on work

The original CPTAC GBM study supplies a relevant multimodal research resource;
its biological findings are not reproduced by counting available features.
Gene-level total protein does not identify proteoforms or phosphorylation
activation, and the historical clinical disease scope is not newly reclassified
by this catalog.
[Wang et al. primary study](https://pmc.ncbi.nlm.nih.gov/articles/PMC8044053/)

A later exploratory benchmark may ask whether RNA improves protein
reconstruction beyond CNV and how performance changes across analytical
plexes. It must freeze its estimator, losses, support, selection and assessment
rules separately. Selection or ranking using source outcomes belongs inside
the corresponding assessment loop when estimating the selected procedure's
performance; a coverage catalog is not such an assessment.
[Ambroise and McLachlan](https://pubmed.ncbi.nlm.nih.gov/11983868/),
[Varma and Simon](https://pubmed.ncbi.nlm.nih.gov/16504092/)

This profile establishes no association significance, FDR control, causal
regulation, novel glioma target, clinical utility, aligned external biological
validation or AlphaFold-scale capability. Processing/reference compatibility,
genetic donor independence and biological transport remain separate questions.
