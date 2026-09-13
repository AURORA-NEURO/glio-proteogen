# Longitudinal GBM SPHINKS signature-transition concordance

## Claim boundary

`kncc-gbm-longitudinal-kinase-transition/1.0.0` is an additive,
research-use-only comparison of caller-supplied PDC000515-compatible
phosphosite transitions with source-fitted SPHINKS signature directions. A
kinase name identifies a published SPHINKS signature. The result is **not** a
measurement of kinase activity or biochemical activity, does not establish a
causal regulator, does not predict recurrence, and is not evidence independent
of PDC000515. It does not replace the raw-phosphosite longitudinal lane.

Every estimable result is `limited`; an inestimable result is `abstained`. The
runtime never emits a `supported` state.

## Locked sources and fitted artifact

The importer in `tools/import_kncc_longitudinal_kinase_transition.py` fails
closed against the already admitted PDC000515 phosphosite artifact, its exact
SPHINKS crosswalk, the fixed HGNC mapping, and the canonical SPHINKS
Supplementary Tables 5a/5d source profile. The key bindings are:

- PDC study `PDC000515`, version UUID
  `e5e0dd84-f982-46e3-b78a-5cb19eef31a8`;
- fitter source SHA-256
  `sha256:ccddb71c2bc92a853d4c0ccdf55b88a50d8f223adf89310d4cacc2c1dff38ab8`;
- PDC source-manifest digest
  `sha256:1b248983791886a9b4522de07d96abb517c416d793b789d435544745dbe6ed34`;
- PDC phosphosite artifact content digest
  `sha256:d31635cc2c9f634679ebd913cf2e0911b0bdff1fb66d53533239e870d4b8624a`;
- PDC-to-SPHINKS crosswalk digest
  `sha256:4d9d62c63361f285b45fff380588b37174663bfc702cef0587b705aaadebe8c4`;
- HGNC mapping digest
  `sha256:07245f3fe73129607856b1a92671cce13932a53c95a19f16894daf4971449aa4`;
- SPHINKS source SHA-256
  `sha256:865a2db1ec99dcf047d6ff56b313a21607b840e5239bb9184739f6f6f217fb88`;
- SPHINKS signature-edge digest
  `sha256:2cba909989a33438e5d81c551015300b5de7553fa7275b1d5dffde6bf134b345`;
- SPHINKS fixed master-kinase digest
  `sha256:cf723900c41a0d0c42347658bc9fe618556487f86eff88b3567b1566e0fd5f4c`.

The packaged canonical artifact is 1,271,736 bytes. Its byte SHA-256 is
`5e14278cca4d179bc6585abcc698704bf213fb81885a8a6876a5f1741ac4c82d`,
its content digest is
`sha256:416a5f814378ed141fc89d3dd4bf497489c472cef2db1c16e97ec9ede080c822`,
and its 64-member patient-bootstrap ensemble digest is
`sha256:c5756048bce4074efe9b1914c325b0cbb5f312e7840efe92d8b926edbb5df38c`.
It contains aggregate parameters only: no patient identifiers, reversible
patient-derived hashes, patient-level matrices, or patient-level projections.

Kim et al., *Integrated proteogenomic characterization of glioblastoma
evolution*, Cancer Cell 42(3):358-377.e8 (2024), DOI
10.1016/j.ccell.2023.12.015, is the PDC000515 study attribution. Migliozzi et
al., *Integrative multi-omics networks identify PKCδ and DNA-PK as master
kinases of glioblastoma subtypes and guide targeted cancer therapy*, DOI
10.1038/s43018-022-00510-x, is the SPHINKS attribution. Both source adaptations
are recorded as CC-BY-4.0 with explicit GLIO-PROTEOGEN transformation notices.

## Source fit

The locked cohort contributes 88 strict paired transitions. The admitted
background contains 2,457 source families; the crosswalk contains 8,779 exact
PDC rows and 8,533 unique families, including 246 additional rows from exact
label collisions. SPHINKS signatures map 608 source rows into 572 unique
families. Composite source rows remain indivisible.

The fit uses a fixed family of 24 SPHINKS kinase hypotheses. Training-fold
processing applies Huber location, MAD/support variance floors, inverse
signature-membership multiplicity, and a competitive two-sided null stratified
by exact residue composition and composite cardinality. Benjamini-Hochberg is
computed over all 24 hypotheses with unestimable hypotheses represented as
`p=1`; selection uses `q <= 0.10` and at least three mapped families. Kinases
are averaged within subtype and then the represented subtypes are weighted
equally. All admission, scaling, null construction, and weights are fitted on
training patients inside grouped validation folds.

The full fit selected 12 signatures. Held-pair validation fits feature
admission, scaling, competitive nulls, signature selection, and weights only on
outer-training pairs; it never intersects eligibility with the full-cohort
release inventory. Eleven full-fit signatures satisfy the frozen bootstrap
selection-frequency threshold of 0.80. `CHEK2` is explicitly
`selected_unstable` with frequency 0.546875 and therefore remains LIMITED when
estimable. The 64 patient-bootstrap models preserve joint sparse selection,
weights, and replicate-specific transition scales. Those bootstrap refits are
explicitly conditional on the final frozen release-eligible inventory and are
uncertainty/stability approximations, not validation.
Every full, outer, nested-comparator, and bootstrap Huber refit is required to
converge; the importer aborts rather than serializing a partial fit. All 64
bootstrap refits pass that executable gate in the frozen artifact.

## Locked evaluation and stability

Five-fold patient-grouped evaluation held every pair out from every fitted
preprocessing and selection step:

- signature-transition direction recovery: 68/88, or 0.7727272727, Wilson 95%
  interval `[0.6748572348, 0.8477825470]`, pooled median sign margin
  0.4829230246;
- raw-phosphosite axis on the same folds: 70/88, or 0.7954545455;
- signature-only correct pairs: 7; raw-axis-only correct pairs: 9;
- exact two-sided McNemar p-value: 0.8036193848;
- held-pair score Pearson correlation: 0.6109301534; sign agreement:
  0.8181818182.

These results do not show added independent evidence. Repeated held-pair
results are not treated as independent observations and are not external
validation. Bootstrap selected-set Jaccard similarity has median 0.8571428571
and minimum 0.5555555556; the complete full-fit set is recovered in only
0.296875 of replicates. Full-set stability and interval-calibration gates
therefore remain false.

## Runtime semantics

The request requires the exact typed PDC000515 TMT11 unshared-peptide log2-ratio
assay attestation and a single normalization-reference binding across ordered
time points. Exact phosphosite IDs and their HGNC symbols must match the locked
catalog. Missing and unsupported values are ignored and cannot become negative
evidence. Left-censored values are counted but excluded from point scoring;
they are not imputed. Composite source groups are kept whole.

Deterministic uncertainty combines each caller observation perturbation with
the corresponding patient-bootstrap model and its own scale. The measurement
perturbation currently assumes featurewise-independent Gaussian errors and
combines the marginal from/to standard errors in quadrature. The request cannot
represent shared-reference, TMT, batch, or other covariance blocks, so the
runtime cannot claim calibrated joint measurement uncertainty.

The receipt reports fixed-hypothesis q-values, frozen selection state, mapped
coverage, signature/subtype/overall intervals, top exact-family drivers, and
three source-processing/model ablations: equal kinase weighting instead of
equal subtype weighting, removal of composite source groups, and removal of
inverse-multiplicity correction. Source-selected state is preserved even when
runtime evidence abstains.

## Interfaces

The stateless HTTP lane is mounted at:

- `GET /v1/research/longitudinal-gbm-kinase-transition/profile`
- `GET /v1/research/longitudinal-gbm-kinase-transition/demo`
- `POST /v1/research/longitudinal-gbm-kinase-transition/analyze`
- `POST /v1/research/longitudinal-gbm-kinase-transition/verify`

The matching CLI group is `glio-proteogen
longitudinal-gbm-kinase-transition profile|demo|analyze|verify`. Analyze requests
are limited to 2 MiB, results to 4 MiB, replay envelopes to 8 MiB, and execution
to two concurrent 120-second jobs. Replay recomputes the exact profile-bound
receipt; the service persists neither requests nor results.
