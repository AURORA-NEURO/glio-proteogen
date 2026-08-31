# CPTAC GBM matched protein/phosphosite evidence-graph replacement design

## Status and replacement boundary

This is a source-audit and preregistered design, not a fitted model, admitted
source catalog, or release artifact. It does not add an inference lane or change
the twelve-lane maturity count. No patient-level value, label, identifier,
fold assignment, or raw source byte is added to the repository by this design.

The proposed lane is reserved as
`cptac-gbm-matched-protein-phosphosite-ecgi/1.0.0` only if every admission gate
below passes. Its narrow purpose is to replace the repository-authored 64-node
demo topology and fixed relation-weight demonstration behind `glio-ecgi/1.0.0`
with a source-fitted, glioma-scoped protein/phosphosite concordance profile. The
existing ECGI numerical solver is real and remains the intended inference core;
the synthetic demo topology is the replaceable part. This work must not redirect
or relabel a governed M09/M10 route, the PDC000514 protein-only participant-set
lane, or the no-fusion KNCC composition surface.

## Read-only candidate-source audit

The audited local directory was
`.codex-tmp/cptac-gbm-joint-source`. The directory contains six files and no
download receipt, PDC file manifest, study-version manifest, license record, or
case/specimen map. The following byte locks were independently recomputed on
2026-08-30. “Candidate role” records the intended capture association; the
bytes themselves do not encode a PDC study ID and therefore do not yet prove
that association.

| Candidate role | Local file | Bytes | SHA-256 |
|---|---|---:|---|
| PDC000204 protein matrix | `CPTAC3_Glioblastoma_Multiforme_Proteome.tmt11.tsv` | 48,440,330 | `fc7c7b595211b81482db9281fb1592e58492eef87ab7db1fd64f7e4ec3bc96bd` |
| PDC000204 protein sample map | `CPTAC3_Glioblastoma_Multiforme_Proteome.sample.txt` | 3,795 | `faea4574cd423c54b064c201391a9591160dc98ac3b6a443adaf8975914d74d1` |
| PDC000204 protein summary | `CPTAC3_Glioblastoma_Multiforme_Proteome.summary.tsv` | 3,440,988 | `fb720446fc749a55d9bef97830d94e2412f11a74a5909e2ffc11c43ca6742911` |
| PDC000205 phosphosite matrix | `CPTAC3_Glioblastoma_Multiforme_Phosphoproteome.phosphosite.tmt11.tsv` | 40,120,930 | `49b20d25b63ee5785ec9340420dc0482a834c89f36f996a0e9cf4b7eda2298e2` |
| PDC000205 phosphoproteome sample map | `CPTAC3_Glioblastoma_Multiforme_Phosphoproteome.sample.txt` | 3,869 | `5b5567ae9df8bcd3abed5dc1e219bb50403f021a83053e6c20585e8f52567f13` |
| PDC000205 phosphoproteome summary | `CPTAC3_Glioblastoma_Multiforme_Phosphoproteome.summary.tsv` | 2,038,094 | `297972bc5ac7eec63d0da50f357210f0f0b15136c1d8e93e158c45db712f5d0e` |

The byte-level and table-level checks establish the following facts, and only
these facts:

- each sample map has 11 non-empty TMT11 plex records, ten non-pool channels per
  plex, `POOL` in channel `126C`, and label reagent `SG252258_SH258846`;
- the protein sample map has one additional terminal record on physical line 13
  whose 15 fields are all empty. A future exact-source parser may ignore exactly
  that locked record after verifying the file hash; it must not generally skip
  malformed or partial rows;
- after excluding that one all-empty record, the two maps contain the same 110
  unique non-pool labels in the same order. The protein matrix's 110
  `Unshared Log Ratio` headers, its 110 companion `Log Ratio` headers, and the
  phosphosite matrix's 110 `Log Ratio` headers bind to that order exactly;
- this is an exact **aliquot-label match**, not yet a patient match. String
  prefixes or suffixes are not an admitted case identifier;
- the protein matrix contains three non-feature rows (`Mean`, `Median`, and
  `StdDev`) followed by 10,977 unique human gene rows. Its summary contains the
  same 10,977 genes exactly. Across the primary unshared-ratio block, 1,148,949
  cells are finite and 58,521 are blank (4.8466%); 8,973 genes are complete in
  all 110 columns;
- the phosphosite matrix contains 41,580 unique human row identifiers over
  5,803 gene labels. It has 1,732,806 finite cells and 2,840,994 blanks
  (62.1145%); 2,794 rows are complete in all 110 columns. The source preserves
  33,957 single-site rows, 6,315 two-site rows, and 1,308 three-site rows. Thus
  7,623 rows are composite site groups and must not be split. Another 4,724 rows
  carry multiple source peptide strings and must not be multiplied into
  independent observations;
- the phosphoproteome summary has 6,620 unique human genes. It contains every
  one of the 5,803 quantified phosphosite gene labels plus 817 genes with no
  quantified phosphosite row. Protein and phosphosite matrices share 5,495 gene
  labels; and
- every nonblank quantitative cell parses as a finite number. Source ranges are
  `[-20.2480, 27.9071]` for protein unshared log ratios and
  `[-26.9783, 30.3308]` for phosphosite log ratios. Those are source values, not
  ECGI-standardized effects, and they cannot be passed through the current
  `[-20, 20]` request bound without a training-only transformation.

Blank quantitative cells have no captured limit of detection or censoring
threshold. They are therefore `missing`, never zero and never
`left_censored`. The files also provide no site-localization probability,
measurement-level standard error, or phosphosite occupancy. Those quantities
must not be invented.

## What the existing PDC000204 metadata does and does not bind

The separate checked-in metadata fixture
`research/fixtures/pdc/pdc000204.metadata.json` is 2,158 bytes with SHA-256
`92857eea5d705a4703c81203b3ec37f40c765c3eb1a061c7a1858c0c8e2a053a`.
Its canonical JSON digest is
`sha256:ed3fcc96a94e3d14733ce75ca04adc992560aa3ec5f00168c8b77829857b0918`.
The associated 1,082-byte manifest has SHA-256
`d8000e2d43cd9ff55e4cc775d6c9c8d39a2445469752b49688c6b985cf810e01`;
its declared raw-byte length/hash and canonical/response digests all reproduce.

That fixture identifies `PDC000204`, study UUID
`cfe9f4a2-1797-11ea-9bfa-0a42f3c845fe`, analytical fraction `Proteome`,
experiment type `TMT11`, and structured counts of 111 cases and 111 aliquots.
Its narrative describes tissue from 99 GBM patients and normal brain from ten
GTEx participants. Neither the structured count, that narrative, nor the 110
captured labels can be reconciled from the available files. The fixture is
metadata-only and does not bind any of the six candidate files to a PDC file
record or version.

There is no corresponding local PDC000205 metadata/source manifest in the
audited inventory. Therefore the phrases “PDC000204 protein” and “PDC000205
phosphoproteome” remain candidate capture attributions until exact PDC
study-version and file records are captured and verified.

## Topology sources and fixed glioma scope

The replacement must not learn which biological domains to include from these
110 samples. It will reuse two already admitted, pre-outcome topology seed
inventories, but will rebuild every feature projection against the new source:

| Seed inventory | Bytes | File SHA-256 | Canonical content digest |
|---|---:|---|---|
| exact ten-event glioma-domain pathway seed, `kncc_reactome_transition_source.v1.json` | 34,279 | `8446a9d923e047f0d4df9d190daca18f20faa932c471710efb733b8e2b1e631c` | `sha256:0d0ad7b572aabed7049f302a44380166135cb2fed1527fe845a19457a8cbcdc6` |
| exact 28-row pilot complex seed, `kncc_reactome_complex_transition_source.v1.json` | 96,157 | `03fc954944af058d6f8d4ec629e16615555791642b7d91bc1d0d1455e1dbcf30` | `sha256:5719f23be05e7b1603cd5ba56deb638f90300686ada786bec22a2201a7f99124` |

The ten pathway roots remain exactly `R-HSA-177929`, `R-HSA-186797`,
`R-HSA-198203`, `R-HSA-165159`, `R-HSA-5683057`, `R-HSA-1640170`,
`R-HSA-73894`, `R-HSA-1234174`, `R-HSA-1474244`, and `R-HSA-168249`.
The 28 complex stable IDs, tiers, exact direct pathway bindings, and selection
ledger are the seed artifact's exact rows; its PDC000514 feature indices and
eligibility fields are not reusable evidence for this cohort.

The following local annotation bytes were also recomputed and are the only
permitted inputs to the new topology projection:

| Annotation source | Bytes | SHA-256 |
|---|---:|---|
| `ReactomePathways.gmt.zip` | 298,479 | `8c1dbc8578431da5d2d5118262718c60b553a9be3398e93658daa069e4a9afd4` |
| `gmt/ReactomePathways.gmt` | 1,032,186 | `89983d5c1f0af11c52edfeee7323eb425580ac6281d387a528562ab1787ce56b` |
| `ReactomePathways.txt` | 1,592,393 | `f6d7a2bf89b5bcfe0250a0bc7f51bff94641447911712b8ff129f5b55e52df3a` |
| `ReactomePathwaysRelation.txt` | 634,259 | `fd49a624d80c14eb37ae57a02e141d574d5ede3f60022bb99edbd909448a3f1e` |
| `ComplexParticipantsPubMedIdentifiers_human.txt` | 3,690,987 | `ad536e76c39772964a4e225a848acfce6c1e0f3232393d903bc59358a1c8987c` |
| `Complex_2_Pathway_human.txt` | 1,168,246 | `99af18181f9e79f54a136235339142421d1a4ccaa7535f92abad63c0dfde95c3` |
| `hgnc_complete_set.txt` | 16,948,224 | `854162118530e929f06249f3349465dd5fe0515fcccf0347f463e833609c1270` |

As in the existing source admissions, “Reactome V97” is acquisition-context
attestation; the files do not encode the release number, so their exact hashes
are authoritative. The new source artifact must preserve direct memberships
and direct complex/pathway bindings. Hierarchy is annotation unless a separately
source-justified numerical direction is admitted. Reactome membership does not
establish activation, a signed regulatory effect, or essential subunits. Every
complex member therefore has `essential=false` in the numerical graph.

No kinase-substrate source is present in this capture. The replacement has no
kinase nodes, kinase-substrate edges, kinase activity, or kinase feedback. A
phosphosite row's source `Gene` field may bind it to a parent gene product for
provenance and protein adjustment, but `site_of` remains annotation-only: it is
not a numerical assertion that total protein and phosphorylation move together.

## Patient and specimen grouping contract

The source fitter must consume an exact-hash PDC biospecimen manifest for both
studies. The authoritative grouping key is the PDC `case_id`, not a substring of
the `CPT...` label. The admissible cohort is formed as follows:

1. remove the `126C` pooled-reference channels;
2. join assays only on an exact aliquot identifier that maps to the same official
   `case_id`, `sample_id`, specimen, sample type, and analyte-compatible aliquot
   relationship in both versioned study manifests;
3. group every aliquot, technical repeat, and specimen from one `case_id` into
   the same split before any value-dependent operation;
4. retain one prespecified primary-tumor specimen per case. If several remain,
   use the official analyte/aliquot hierarchy and a source-locked deterministic
   priority rule; never select by completeness or abundance;
5. fit the primary model only on pathologically admitted GBM tumor cases. Normal
   brain/GTEx samples are a prespecified non-target sensitivity set, never
   pooled with tumors, never used to tune the model, and never called external
   validation; and
6. require at least 80 strict matched tumor case groups. Fewer groups block this
   design rather than trigger a weaker split or an unplanned cohort expansion.

The evaluation split is five deterministic, batch-balanced outer case-group
folds with four inner case-group folds. The assignment algorithm and seed are
profile-bound; patient labels, label hashes, fold membership, and per-patient
predictions are not shipped. The final source fit may use all admitted tumor
groups only after the nested evaluation is frozen and passes.

## Exact measurement representation

- Protein primary evidence is `Unshared Log Ratio`. The companion `Log Ratio`
  block is a mandatory source-processing ablation, not a second independent
  modality.
- A phosphosite row is the exact source row. Composite site groups and alternate
  peptide lists remain atomic. No single-site localization, isoform transfer, or
  peptide independence is inferred.
- Source gene symbols are mapped one-to-one through the locked HGNC table.
  Ambiguous, withdrawn-to-multiple, absent, or non-human mappings are
  `unsupported`, never guessed.
- Within every training fold, each feature is robustly centered and scaled.
  Zero-scale or insufficient-support features are unsupported. Held-patient
  values never participate in centering, scaling, feature eligibility, or
  loading estimation. No cohort-wide quantile normalization or imputation is
  allowed.
- A protein feature is eligible only when it is finite in at least 80% of the
  outer-training case groups. A phosphosite row is eligible only when it and its
  mapped parent protein are co-observed in at least 40 outer-training case groups
  and at least 50% of that fold. These gates are recomputed without the held
  groups in every fold.
- For a phosphosite row `s` whose parent gene `g` has matched protein evidence,
  fit the training-only Huber regression
  `site_ratio_s = alpha_s + beta_s * protein_ratio_g + error_s`. The residual is
  the phosphosite input. It is explicitly a **protein-adjusted relative
  phosphosite signal**, not occupancy. If either value is missing or the
  regression lacks support, that site observation is missing/unsupported.
- The source has no measurement-level standard errors. Feature-specific robust
  residual scales and their bootstrap variability may supply model-derived
  observation uncertainty, but must be named as such. They are not analytical
  replicate error bars.
- Source blanks remain missing. No left-censor bound is learned from this
  capture. A standardized value outside the ECGI request domain causes an
  explicit out-of-profile abstention; it is not silently clipped.

The common TMT reference may have been constructed or processed using the
source cohort. Until the exact processing protocol is locked, nested evaluation
on these provided ratios is at best cohort-transductive at the upstream
normalization layer, even when every repository-side transformation is fitted
inside folds.

## Model family and bounded graph semantics

The only admissible family is a missing-aware robust confirmatory set-factor
model followed by the existing ECGI directed conditional-IRLS solver:

1. For each exact pathway or complex participant set, fit separate protein and
   protein-adjusted-phosphosite rank-one Huber factors. Loadings are zero outside
   exact source membership, ridge-regularized toward the equal-membership
   comparator, normalized to unit norm, and oriented so their dot product with
   the equal-positive membership vector is nonnegative. Overlapping features
   receive inverse-membership-degree weights. The factor Huber delta is `1.345`,
   the loading-to-equal-membership ridge is `0.025`, and the coordinate ridge is
   `0.075`.
2. Project each caller sample to a protein set coordinate and a phosphosite set
   coordinate with missing-aware robust loss and explicit support. This
   compression keeps each ECGI request within its existing 256-node bound; it
   does not turn the set coordinate into a pathway-activity truth label.
3. Feed those coordinates to unchanged ECGI Huber inference. The numerical edge
   families are protein-coordinate to pathway, phosphosite-coordinate to
   pathway, protein-coordinate to complex, and complex to its exact directly
   bound pathway. Learned loading sign supplies concordance orientation, not
   causal direction. Site-parent and pathway-hierarchy links remain
   annotation-only.
4. Select one nonnegative multiplier per numerical edge family from the exact
   grid `{0, 0.25, 0.5, 1, 2}` inside the inner folds. Zero removes a family.
   The deterministic tie break chooses the lower-complexity vector: fewer
   nonzero families, then smaller squared norm, then lexicographic order. No
   patient-, feature-, pathway-, or edge-specific reliability is tuned outside
   the training fold.
5. Use the existing ECGI Huber delta `1.345` and ridge penalty `0.035`. Refit all
   preprocessing, protein adjustment, factor loadings, and family multipliers
   in each outer fold and in each of 256 case-group bootstrap refits. The final
   artifact may contain aggregate loadings, family multipliers, and bootstrap
   parameter draws only after redistribution/privacy admission; it must contain
   no patient values, identifiers, identifier-derived hashes, folds,
   coordinates, predictions, residuals, or resample indices.

All numerical ECGI edges are positive concordance edges after factor
orientation; there are no learned regulatory signs. The existing ECGI
`member_of=0.90` and `participates_in=0.80` relation weights remain the base
weights, multiplied by the selected family multiplier. A zero multiplier omits
the family before request construction. The source-fitted adapter and its
weights require a new content-bound profile, but the ECGI solver iterations,
loss, censor handling, convergence, per-request measurement bootstrap, and
ablation semantics are not changed. The 256 case-group source refits quantify
fitted-source parameter sensitivity in a separate outer ensemble; they are not
relabeled as ECGI measurement bootstrap draws.

A pathway factor requires at least five eligible protein genes and eight
eligible phosphosite rows spanning at least four parent genes. A complex factor
requires at least three eligible protein genes and three eligible phosphosite
rows spanning at least two parent genes. At runtime, each contributing modality
must supply at least three finite observations and at least 30% of that factor's
absolute fitted-loading mass. Otherwise the joint coordinate abstains; a
protein-only fallback remains explicitly single-modality and cannot satisfy a
matched-lane endpoint.

This is a confirmatory reconstruction/concordance model. It is not an
unrestricted graph neural network, outcome-supervised classifier, clinical
endpoint model, kinase model, or causal graphical model.

## Leakage controls and comparators

Every operation that reads quantitative values is training-only: feature
support, robust location/scale, protein adjustment, set-factor loadings,
family-reliability selection, missingness thresholds, uncertainty, and support
cutoffs. Reactome root/complex selection is locked before value access. Feature
mask folds are deterministic functions of the public feature identifier and
profile seed, not measurement values. Test patients cannot contribute to a
source pool, preprocessing statistic, edge weight, bootstrap fit, or stopping
decision within repository control.

The following comparators and negative controls are mandatory and use the same
outer folds and feature masks:

- training-median, parent-protein-regression, protein-only, phosphosite-only,
  and equal-membership set-factor baselines;
- degree-, set-size-, modality-, and observation-coverage-stratified topology
  permutation, using 256 profile-seeded full refits;
- wrong-pair protein/phosphosite joins permuted within TMT plex, which preserve
  batch and marginal missingness while destroying the exact aliquot match,
  using 256 profile-seeded within-plex derangements and full refits;
- complete refits omitting protein, phosphosite, complexes, overlap correction,
  protein adjustment, and the unshared-protein choice; and
- an 11-run leave-one-plex-out sensitivity and a batch-only predictor. These do
  not create an external cohort, but expose a model whose apparent gain is a
  plex effect.

No clinical, molecular-subtype, survival, recurrence, or treatment field may be
used for selection, tuning, or evaluation in this lane.

## Endpoints and prespecified admission gates

The primary endpoint is masked phosphosite reconstruction in outer-held
patients. Eligible phosphosite rows are partitioned into five profile-bound
feature folds. For each fold, the joint graph receives all eligible protein
evidence and the other four-fifths of phosphosite evidence and predicts the
masked protein-adjusted phosphosite residuals. Absolute standardized errors are
aggregated first within patient and then across case groups, so heavily observed
sites or patients do not dominate.

The primary comparator is the strongest of the phosphosite-only,
parent-protein-regression, equal-membership, and training-median baselines on
the exact same cells. Admission requires both a median patient-level relative
MAE reduction of at least 2% and a strictly positive lower endpoint of the 95%
case-group bootstrap interval from 10,000 deterministic resamples. A pooled-cell
result cannot satisfy this gate.

Secondary endpoints are masked protein reconstruction, patient-balanced
Spearman correlation, 90% bootstrap prediction-interval coverage and interval
score, performance at 10%, 30%, and 50% additional modality-stratified
missingness, and leave-one-plex-out performance. The fixed ten-pathway family
uses 10,000 deterministic patient-level paired sign-flip draws with a plus-one
pseudocount and Benjamini-Hochberg FDR at `q <= 0.10`; a pathway that fails its
family gate must abstain rather than inherit the global result. A 90% interval
passes only when patient-balanced empirical coverage is in `[0.80, 0.98]`, 0.90
lies inside its 10,000-resample 95% case-bootstrap interval, and its median
interval score is no worse than the strongest comparator. The joint gain must
remain positive after 30% additional missingness, be positive in at least nine
of the 11 leave-one-plex-out runs, and have positive median leave-one-plex-out
gain. The 50% missingness run is a reported stress result, not a hidden tuning
criterion. Every surviving estimate is still capped `LIMITED` because all
evaluation is internal and shares upstream source processing.

The correct-pair model must beat its within-plex wrong-pair negative control and
the degree/coverage-matched topology permutation under the same global
patient-level gate; its gain must also exceed the 95th percentile of each
256-refit negative-control gain distribution. The batch-only predictor must not
satisfy the primary gate. If cross-modal input does not beat the strongest
single-modality comparator, the matched model remains `not_fitted`; the result
must be recorded as a negative feasibility audit rather than released as a
multimodal lane.

## Claim ceiling

The maximum claim is:

> internal source-cohort, protein-adjusted matched protein/phosphosite
> Reactome-set concordance with patient-grouped reconstruction evidence

It is not pathway activation or flux, complex assembly or stoichiometry,
phosphosite occupancy, biochemical kinase activity, a causal mechanism,
single-cell state, GBM subtype, diagnosis, prognosis, recurrence, treatment
response, target nomination, or a clinical decision. Exact assay pairing does
not make the modalities statistically independent. Internal nested validation,
normal-brain sensitivity, and deterministic replay are not external validation.

## Admission blockers

Implementation and any model artifact are blocked until all of the following
are resolved:

1. **PDC file provenance:** capture exact PDC000204 and PDC000205
   study-version UUIDs and a file-level manifest binding each of the six names,
   byte sizes, source MD5/SHA-256, stable file IDs/URLs, retrieval time, and
   processing category to the locked local bytes.
2. **Case/specimen identity:** capture official case/sample/aliquot relationships
   for both studies and reconcile the 99-plus-10 narrative, 111 structured
   PDC000204 cases/aliquots, and 110 local assay labels. No label-substring
   heuristic is acceptable.
3. **Cohort semantics:** source-lock tumor/normal, specimen, analyte, technical
   replicate, pathology, and exclusion fields. Demonstrate at least 80 strict
   matched tumor case groups without selecting by completeness.
4. **Processing and uncertainty:** source-lock the TMT normalization/reference
   protocol, protein-group rule, phosphosite localization/composite semantics,
   and missing-value meaning. If censoring bounds or localization confidence are
   unavailable, the model must retain the conservative missing/composite rules
   above.
5. **Topology projection:** generate and independently reproduce a compact
   source artifact binding the exact Reactome/HGNC bytes, ten roots, 28 complex
   seeds, new gene/site projections, exclusions, direct bindings, and every
   annotation-only versus numerical edge. It must be constructed without
   reading patient abundance values.
6. **License, privacy, and redistribution:** capture terms for both processed
   matrices and determine whether aggregate fitted loadings/bootstrap parameters
   may be distributed. Until approved, offer only an exact-hash user-side local
   fitter; never vendor these matrices or a patient-derived artifact by default.
7. **Numerical semantics:** demonstrate that the set-coordinate adapter preserves
   ECGI's missing/censored/support contracts and 256-node bound, that unsigned
   annotation is not converted into signed regulation, and that all four learned
   edge families can be removed by ablation.
8. **Evaluation:** pass the primary cross-modal, negative-control, batch, support,
   calibration, and deterministic-replay gates above. A failure leaves the lane
   absent, not merely relabeled.
9. **External evidence:** no blocker above can create external validity. A
   separately source-locked cohort and frozen transport protocol are required
   before any generalization, subtype, prognosis, or clinical-performance claim.

Only after blockers 1–8 pass may an additive research surface provide
`profile`, wholly synthetic `demo`, `analyze`, and exact `verify` operations with
immutable source/topology/model/profile digests, full modality/topology
ablations, abstention, and the literal claim ceiling above.
