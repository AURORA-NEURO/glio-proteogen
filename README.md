# GLIO-PROTEOGEN

Repository code and bundled research-data derivatives do not necessarily share
one license. Source-specific attribution, license, and transformation notices
are recorded in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and in each
research artifact's provenance block.

GLIO-PROTEOGEN is a clean-room, contract-driven research platform for resolving glioma
biology at the protein, proteoform, complex, and pathway levels while preserving genomic
context, transcript-protein disagreement, uncertainty, provenance, and treatment history.

The repository is being built from an empty history, one bounded module at a time. A module
is considered implemented only when its public contracts, executable behavior, locked
fixtures, adversarial evaluations, microbenchmarks, traceability, and safe-failure behavior
are all present.

See [CLEAN_ROOM.md](CLEAN_ROOM.md) for the construction boundary and
[CONTRIBUTING.md](CONTRIBUTING.md) for the module evidence workflow.

## Scientific boundary

GLIO-PROTEOGEN may emit a proteogenomic state, proteotype, or protein-level subtype object.
Governed M16 does **not** own kinase-state inference, generic all-omics fusion, or treatment
recommendations. The separate `glio-ecgi/1.0.0` research lane may emit explicitly experimental,
local kinase estimates from caller-supplied phosphosite topology; those estimates never become
governed or prescriptive claims. Missing or unsupported evidence is never converted into a
negative finding. The separate `gbm-proteomic-axes/1.0.0` lane runs seven exact, published
glioblastoma protein-abundance ensembles for continuous KRAS-like, MYC-like, hypoxia, Verhaak,
and EGFR program scores. Those outputs remain bulk-proteome research evidence rather than cell
fractions, diagnoses, or treatment predictions. The `neftel-protein-programs/1.0.0` lane maps
standardized bulk-protein contrasts to the exact eight Neftel Table S2 programs with robust
location, independent rank enrichment, deterministic permutations, FDR control, bootstrap
intervals, marker-family ablations, and explicit coverage-based abstention. It does not relabel
bulk tissue as single cells or infer cellular fractions.
The `sphinks-gbm-master-kinase-concordance/1.0.0` lane compares standardized
phosphosite contrasts with 24 subtype-specific master-kinase signatures from
Migliozzi et al. using one-sided robust location, residue-stratified competitive
permutations, fixed-family FDR control, bootstrap uncertainty, and ablations. It
is independently authored concordance evidence—not an exact SPHINKS port,
calibrated kinase activity, subtype probability, or treatment guidance.
The `migliozzi-gbm-functional-proteotype/1.0.0` lane jointly fits relative GPM,
MTC, NEU, and PPR concordance coordinates from exact Table 2d protein
signatures, with one-sided censoring, fixed-family rank evidence, deterministic
bootstrap uncertainty, and source/driver ablations. Table 2e pathways remain
source-cohort context only; the lane does not infer a categorical subtype,
sample pathway activity, or a clinical state. See
[`docs/research/gbm-functional-proteotype.md`](docs/research/gbm-functional-proteotype.md).
The additive `/v2/research/modules/m10/functional-proteotype` facade exposes
that exact fitted request/result/replay contract at the M10 research boundary,
with explicit eight-module responsibility mappings and no change to governed
M10 routes or digests. See
[`docs/research/m10-functional-proteotype-facade.md`](docs/research/m10-functional-proteotype-facade.md).
The `kncc-gbm-longitudinal-concordance/1.0.0` lane scores ordered protein
profiles against a de-identified axis fitted from 104 strict matched
primary/recurrent PDC000514 GBM pairs. It uses patient-grouped nested
cross-validation, one-sided censor constraints, coupled measurement and
coefficient uncertainty, exact source and driver ablations, and exploratory
heteroscedastic-Huber PELT. Its output is source-cohort concordance—not a tumor
evolution, recurrence, prognosis, or treatment-response determination.
The additive
`/v2/research/modules/m15/longitudinal-recurrence-proteotype` facade exposes
that exact request/result/replay contract at the M15 research boundary. It can
replace only synthetic or digest-derived longitudinal scores and does not
predict recurrence, infer clonal evolution, or change governed M15 routes or
digests. See
[`docs/research/m15-longitudinal-recurrence-facade.md`](docs/research/m15-longitudinal-recurrence-facade.md).

The `kncc-paired-phosphosite-transition/1.0.0` research lane is fitted from 88
strict PDC000515 primary/recurrent pairs with patient-grouped nested validation,
composite-site preservation, exact source locks, and a conservative SPHINKS
site/peptide crosswalk. It is exposed through stateless API, CLI, and workbench
interfaces with exact replay. Feature-selection instability and the absence of
independent interval calibration keep estimable outputs `LIMITED`; protein
adjustment, phosphosite occupancy, kinase inference, and cross-assay fusion are
explicitly not fitted. See
[`docs/research/longitudinal-gbm-phosphosite-foundation.md`](docs/research/longitudinal-gbm-phosphosite-foundation.md).

The `kncc-gbm-longitudinal-kinase-transition/1.0.0` lane evaluates those same
PDC000515 transitions against the fixed 24-signature SPHINKS family using
training-only robust fits, residue/composite-stratified competitive nulls,
fixed-family FDR control, and patient bootstrap uncertainty. It reports
same-assay signature-transition concordance only. It is neither an independent
validation source nor biochemical, causal, or treatment-relevant kinase
activity, and every estimable result remains `LIMITED`.

The `kncc-reactome-conditional-transition/1.0.0` lane uses 104 strict
PDC000514 primary/recurrent GBM pairs to fit one global recurrence-concordance
coordinate and 10 Reactome V97 membership coordinates residualized against that
global axis. Its fixed, repository-authored glioma panel is evaluated with eight
held-patient folds and five held-gene folds, solved with bound-aware robust
ridge inference, and packaged with 256 patient-bootstrap source fits. Runtime
results separate measurement and fitted-source uncertainty, preserve one-sided
censoring, expose request-specific reconstruction and structural ablations, and
force overlap-confounded PI3K/AKT evidence to `LIMITED`. These coordinates are
not pathway activation, flux, causal tumor evolution, prognosis, or treatment
evidence. See
[`docs/research/kncc-reactome-conditional-transition-model.md`](docs/research/kncc-reactome-conditional-transition-model.md).

The `kncc-reactome-complex-transition/1.0.0` lane fits 28 separate,
missing-aware robust rank-one coordinates to exact Reactome V97 participant
sets across 11 pilot GBM signaling and stress domains. This is a prespecified
repository-authored pilot panel informed by public glioma biology and the
PDC000514 source paper. It was selected without reading abundance arrays during
import, but is not demonstrated outcome-independent. The locked source artifact
contains aggregate factors learned from the same 104 strict PDC000514
paired-patient transitions, with patient-grouped held-member
evaluation, request-derived measurement and fitted-source bootstrap
uncertainty, one-sided censoring, and four source/member/family ablations. The
held-member factor model improves mean standardized MAE over its training-center
baseline by 20.30% with 72.55% direction accuracy across 14,988 evaluations.
Those metrics support participant-set member-transition concordance only—not
physical assembly, biochemical activity, stoichiometry, essentiality, causal
biology, recurrence prediction, or clinical use. See
[`docs/research/longitudinal-gbm-complex-transition.md`](docs/research/longitudinal-gbm-complex-transition.md).
The additive
`/v2/research/modules/m09/complex-transition-concordance` facade exposes that
exact fitted request/result/replay contract at the M09 research boundary. It
may replace only participant-set transition-concordance stand-ins and cannot
promote them into assembly, stoichiometry, essentiality, activity, causality,
prognosis, or treatment claims. Governed M09 routes and digests remain
unchanged. See
[`docs/research/m09-complex-transition-facade.md`](docs/research/m09-complex-transition-facade.md).

The `kncc-neftel-program-transition/1.0.0` lane fits a global protein-transition
axis and eight conditional program coordinates from 104 strict matched
PDC000514 primary/recurrent GBM pairs, using the exact Neftel Table S2 MES2,
MES1, AC, OPC, NPC1, NPC2, G1/S, and G2/M marker sets. Its deterministic
Huber-IRLS/ridge fit uses patient-grouped outer folds, held-marker evaluation,
128 patient-bootstrap refits, one-sided censoring, fitted-source and measurement
uncertainty, and structural ablations. The fitted dictionary improves on the
global-only comparator but not the simpler equal-membership marker baseline;
therefore every numerical coordinate is explicitly `LIMITED`. These outputs are
same-cohort bulk-protein transition concordance, not single-cell states, cell
fractions, tumor evolution, or clinical evidence. See
[`docs/research/longitudinal-gbm-neftel-transition.md`](docs/research/longitudinal-gbm-neftel-transition.md).

The `glio-ecgi-kncc-gbm-transition/1.0.0` surface composes that exact
PDC000514 Reactome engine with the exact PDC000515 SPHINKS
signature-transition engine as two numerically independent result blocks,
executed deterministically in serial. Its locked factor-graph inventory has 41
nodes and 39 annotation-only containment edges, with zero numerical cross-block
edges. It preserves both child receipts without cross-modal fusion or feedback.
This is an integrated presentation and replay surface, not a new independent
fitted model: Reactome outputs remain
source-cohort concordance rather than activation or flux, and SPHINKS outputs
remain same-source-cohort signature-transition concordance rather than kinase
activity or causality. See
[`docs/research/kncc-gbm-factor-graph.md`](docs/research/kncc-gbm-factor-graph.md).

The `cptac-gbm-cis-dosage/1.0.0` local tool fits five-fold, fold-local Huber
models of `RNA ~ CNV` and `protein ~ CNV + RNA` from exact-hash CPTAC GBM
supplements, then exposes only compact gene-level cohort evidence and exact
replay. Because supplement redistribution terms are not yet admitted, users
must build the artifact from their own exact source copies. The artifact is not
bundled, no public HTTP route is mounted, patient values are never accepted by
the query runtime, and the decomposition is observational rather than causal.
An unmounted
`m07-cptac-gbm-cis-dosage-cohort-evidence/1.0.0` facade now marks this exact
model as the only honest research substitution for M07-04's
scalar-copy/interval-midpoint declaration proxy. It preserves the local-only
artifact boundary and exact receipts; no public M07 route exists while source
redistribution terms remain unresolved. See
[`docs/research/m07-cis-dosage-facade.md`](docs/research/m07-cis-dosage-facade.md).

The separate `cptac-gbm-transcript-protein-discordance/1.0.0` local tool
cross-fits `Protein ~ RNA + CNV` against matched RNA-only, CNV-only, and
training-median comparators for predeclared genes in the same exact CPTAC GBM
cohort. It uses fold-local Huber IRLS, held-out metrics, and 128 deterministic
patient-bootstrap refits to report only cohort-level positive, inverse,
indeterminate, or no-incremental-RNA conditional-association patterns. No
fitted artifact is bundled, no public HTTP route is mounted, and query requests
cannot contain patient measurements. Every estimable result is capped
`LIMITED`; the output is neither biological buffering nor an iProFun
reproduction. See
[`docs/research/cptac-gbm-transcript-protein-discordance.md`](docs/research/cptac-gbm-transcript-protein-discordance.md).

The `gbm-rna-tumor-purity/1.0.0` lane is an exact NumPy port of the published
GBMPurity 5,829→32→16→1 neural model. It accepts raw bulk RNA counts only under
a primary IDH-wildtype GBM attestation, preserves the source 80% gene-overlap
gate and preprocessing, exposes exact active-ReLU local contributions, and
replays every receipt. It estimates one malignant-cell fraction; it does not
infer immune composition or convert protein evidence into cell fractions. The
single released model has no calibrated ensemble, so uncertainty is explicitly
unavailable rather than synthesized. See
[`docs/research/gbm-rna-purity.md`](docs/research/gbm-rna-purity.md).

A separate GBmap-derived GBM composition candidate now has a real
source-independent fitting and inference core: canonical donor/label
pseudobulk aggregation, fold-local stable-marker selection, leakage-safe
whole-study and within-study donor validation, hierarchical
Dirichlet-multinomial signature fitting, adaptive-unknown simplex inference,
calibrated mismatch diagnostics, and an end-to-end training-only candidate
selection protocol. It remains deliberately
`development_unfitted`: the approximately 9 GB admitted source has not been
downloaded, SHA-256 verified, or fitted, no model artifact is claimed, and no
HTTP or CLI runtime is mounted. Its offline extractor is locked to the legacy
AnnData CSR layout, all 338,564 cells, 5,000 source feature keys, 20 exact
`CellID` states, and a leakage-safe 17-batch→16-study mapping. The authoritative
Zenodo file contains 113 raw patient categories while the curated CELLxGENE
asset and final supplement report 110; a complete 113→110 donor crosswalk and
full-file SHA-256 were mandatory gates. The donor gate is now closed from
primary metadata: the three PW032 source samples group to PW032, while the
original Pombo patient table and reporting summary establish `R4 n.c.` as an
additional R4 biospecimen. Both raw R4 labels remain preserved while their
grouped donor key is R4. Exact artifact download, full SHA-256 review,
extraction, fitting, and held-out calibration still remain.
See
[`docs/research/gbmap-deconvolution-source-admission.md`](docs/research/gbmap-deconvolution-source-admission.md).

## Research evidence-graph workbench

The default UI is a linked scientific workbench for the deterministic Evidence-Conserving Graph
Inference engine, the published GBM proteomic-axis models, the Neftel-derived bulk-protein
program model, the SPHINKS-derived master-kinase concordance model, the Migliozzi
functional-proteotype concordance model, the exact published GBMPurity RNA model, and the
source-fitted KNCC longitudinal GBM protein, phosphosite, kinase-signature, and
Reactome conditional-transition models, the 28-participant-set Reactome
complex-transition factor model, the fitted KNCC/Neftel conditional-transition
model, together with the non-fitted KNCC two-block factor-graph composition. It
includes versioned synthetic demos,
structured request editing, graph and
uncertainty inspection, kinase enrichment, proteomic-axis coverage and tree-path explanations,
program-level q-values and marker support, all 24 master-kinase signatures and subtype
aggregates, constrained GPM/MTC/NEU/PPR intervals, functional-proteotype q-values,
driver/ablation explanations, source-only pathway context, GBMPurity feature coverage,
hidden-layer activation traces and exact local ReLU-path contributions, downloadable receipts,
and backend replay verification.
Longitudinal results add interval-supported transitions, source-linked drivers,
source-processing and leave-one-driver-out ablations, change-point stability,
and a phosphosite-specific decomposition of measurement, coefficient, and
interaction uncertainty with exact covariance closure. The Reactome lane adds
global-versus-conditional coordinate views, held-gene reconstruction evidence,
overlap and unique-member support, and fitted-source/measurement uncertainty
without relabeling membership concordance as pathway activity. The KNCC
complex-transition lane adds missing-aware robust member factors, patient-grouped
held-member evaluation, measurement/source uncertainty decomposition, and four
source/topology ablations without relabeling participant-set concordance as
physical complex assembly or activity. The KNCC/Neftel transition lane adds
global-versus-program conditional coordinates, exact-marker coverage,
measurement/source uncertainty, and explicit evidence-grade limitations after
its fitted dictionary failed to beat equal membership. The KNCC
factor-graph view presents both exact child result families and their
content-bound receipts while keeping the two numerical calculations separate.
The original generic OpenAPI explorer remains available at `/api-console`.

Start the UI and API together:

```bash
docker compose up --build --wait
```

Then open <http://localhost:3000>. The API remains on <http://localhost:8000>. Research requests
and results are synchronous and are never persisted server-side. See
[`docs/research/evidence-conserving-graph-inference.md`](docs/research/evidence-conserving-graph-inference.md),
[`docs/research/gbm-proteomic-axes.md`](docs/research/gbm-proteomic-axes.md),
[`docs/research/neftel-protein-programs.md`](docs/research/neftel-protein-programs.md),
[`docs/research/gbm-master-kinase-concordance.md`](docs/research/gbm-master-kinase-concordance.md),
[`docs/research/gbm-functional-proteotype.md`](docs/research/gbm-functional-proteotype.md),
[`docs/research/m10-functional-proteotype-facade.md`](docs/research/m10-functional-proteotype-facade.md),
[`docs/research/gbm-rna-purity.md`](docs/research/gbm-rna-purity.md),
[`docs/research/longitudinal-gbm-protein-concordance.md`](docs/research/longitudinal-gbm-protein-concordance.md),
[`docs/research/m15-longitudinal-recurrence-facade.md`](docs/research/m15-longitudinal-recurrence-facade.md),
[`docs/research/longitudinal-gbm-phosphosite-foundation.md`](docs/research/longitudinal-gbm-phosphosite-foundation.md),
[`docs/research/longitudinal-gbm-kinase-transition.md`](docs/research/longitudinal-gbm-kinase-transition.md),
[`docs/research/kncc-reactome-conditional-transition-model.md`](docs/research/kncc-reactome-conditional-transition-model.md),
[`docs/research/longitudinal-gbm-complex-transition.md`](docs/research/longitudinal-gbm-complex-transition.md),
[`docs/research/m09-complex-transition-facade.md`](docs/research/m09-complex-transition-facade.md),
[`docs/research/longitudinal-gbm-neftel-transition.md`](docs/research/longitudinal-gbm-neftel-transition.md),
[`docs/research/kncc-gbm-factor-graph.md`](docs/research/kncc-gbm-factor-graph.md),
[`docs/research/cptac-gbm-cis-dosage.md`](docs/research/cptac-gbm-cis-dosage.md), and
[`docs/research/cptac-gbm-transcript-protein-discordance.md`](docs/research/cptac-gbm-transcript-protein-discordance.md)
for the algorithms, source provenance, limits, uncertainty semantics, and replay guarantees.
The distinction between real research inference, governed workflow plumbing, and the strict
numerical-stand-in replacement queue is recorded in
[`docs/research/glioma-model-maturity.md`](docs/research/glioma-model-maturity.md).

## Current modules

- `GLIO-PROTEOGEN-M01-01` — protocol and metadata specification. This vertical slice
  provides versioned protocol schemas, strict metadata conformance, explicit unresolved
  states, compatibility rules, provenance, uncertainty, and deterministic audit events.
- `GLIO-PROTEOGEN-M01-02` — sample identity and lineage reconciliation. This module
  resolves only explicit authority-bound identity assertions, validates the closed lineage
  transition graph, preserves pooling and demultiplexing semantics, and quarantines
  contradictions without relabeling upstream records.
- `GLIO-PROTEOGEN-M01-03` — bounded raw-format ingestion. This module verifies exact
  transport checksums, detects gzip and six open proteomic/genomic formats by content,
  performs structural validation, and emits metadata-only descriptors and typed diagnostics.
- `GLIO-PROTEOGEN-M01-04` — deterministic quality metric computation. This module applies
  assay-declared coverage, completeness, detection-limit, control-material, and sample-context
  calculations while preserving missing and censored evidence as explicit states.
- `GLIO-PROTEOGEN-M01-05` — deterministic artifact and contamination detection. This module
  evaluates seven closed technical-artifact classes, emits typed posteriors and flags, and
  produces a deduplicated exclusion mask without interpreting biological absence.
- `GLIO-PROTEOGEN-M01-06` — deterministic harmonization and normalization. This module applies
  reviewed control-median batch and platform shifts while preserving typed missingness and
  enforcing protected biological direction and rank invariants.
- `GLIO-PROTEOGEN-M01-07` — deterministic support-domain and abstention routing. This module
  evaluates eight closed support dimensions and emits typed abstention reasons and remediation
  paths without converting missing or unsupported evidence into a negative finding.
- `GLIO-PROTEOGEN-M01-08` — deterministic provenance and release packaging. This module
  builds canonical USTAR packages from exact content-addressed artifacts, records reproducibility
  metadata and quality/support decisions, and quarantines packages without a digest-bound external
  signature receipt. It does not authenticate the external signer or validate scientific results.
- `GLIO-PROTEOGEN-M02-01` — deterministic peptide-identification protocol metadata
  conformance. This module validates one pinned schema/profile, controlled terms, units,
  cardinality, conditional applicability, and assay/specimen compatibility while preserving
  unresolved mandatory values as quarantined states. It does not establish ontology completeness,
  assay validity, biological correctness, calibration, or clinical readiness.
- `GLIO-PROTEOGEN-M02-02` — deterministic peptide-identification identity-binding audit.
  This module checks opaque artifact bindings against an immutable M01-02 lineage resolution,
  detects swaps, scoped-token collisions, duplicate content, and cross-patient links, and
  preserves unresolved or unsupported bindings as abstentions without re-solving identity.
- `GLIO-PROTEOGEN-M02-03` — deterministic identification raw-input ingestion. This module
  reuses the shared bounded M01-03 parser, then applies explicit identification roles,
  cardinality, and role-to-format rules without retaining bytes or interpreting biology.
- `GLIO-PROTEOGEN-M02-04` — deterministic peptide-identification quality computation. This
  stateless module computes six closed quality metrics from authorized aggregate observations,
  preserves missing, censored, not-applicable, and unsupported states, and emits only a typed
  quality profile with metric-level provenance. It does not parse raw inputs, rescore
  identifications, estimate new q-values, or interpret biology.
- `GLIO-PROTEOGEN-M02-05` — deterministic peptide-identification artifact detection. This
  stateless module evaluates authorized aggregate QC signals under a pinned rule profile, emits
  configured posteriors and technical flags across seven closed artifact classes, and produces a
  deduplicated exclusion mask without interpreting biological absence or changing upstream data.
- `GLIO-PROTEOGEN-M02-06` — deterministic peptide-identification harmonization. This stateless
  module applies eight ordered control-median adjustments, preserves typed unresolved states,
  enforces M02-05 exclusions, and releases only when technical spread falls while declared
  biological direction and rank controls remain within tolerance.
- `GLIO-PROTEOGEN-M02-07` — deterministic identification support and abstention routing. This
  stateless module reduces genuine M02-04 and M02-06 results to compact receipts, then requires
  one reviewed envelope to admit the complete assay, specimen, disease, quality, completeness,
  platform, reference, and intended-use declaration.
- `GLIO-PROTEOGEN-M02-08` — deterministic identification provenance and release packaging. This
  stateless module closes the exact M02-01 through M02-07 result bytes, one minimal typed parent
  protein-subtype receipt, reviewed software/reference/reproduction evidence, and an externally
  verified signature statement into a canonical ten-member USTAR candidate package.
- `GLIO-PROTEOGEN-M03-01` — deterministic protein-inference protocol and metadata
  conformance. This schema-first module binds one reviewed protocol to exact search-space,
  target-decoy, peptide-eligibility, assignment, protein-grouping, ambiguity-preservation, and
  seven-role complex-activity handoff declarations. It validates those declarations without
  searching spectra, assigning peptides, inferring proteins or complexes, estimating error rates,
  or scoring activity.
- `GLIO-PROTEOGEN-M03-02` — deterministic protein-inference identity and lineage
  reconciliation. This schema-first module binds exact M01-02 and M03-01 results to a closed
  content-addressed artifact DAG spanning peptide-evidence, protein-group, ambiguity, and
  complex-activity-input manifests. It detects swaps, collisions, duplicate assignments,
  cross-patient propagation, malformed derivations, and stale producer bindings while preserving
  categorical copy-number concordance as control evidence only. It never relabels upstream
  identity, infers proteins or identity, consumes raw molecular values, or scores complex activity.
- `GLIO-PROTEOGEN-M03-03` — deterministic protein-inference raw-source admission. This bounded
  module closes genuine M01-02, M03-01, and M03-02 receipts over exact mzML, mzIdentML, strict
  protein-group/ambiguity/bundle JSON, five governed FASTA component roles, PSI-MOD OBO, VCF, and
  GFF3 sources. It verifies transport and decoded integrity, structure, cross-references, builds,
  controlled vocabularies, and units without retaining raw bytes or inferring proteins or activity.
- `GLIO-PROTEOGEN-M03-04` — deterministic protein-inference quality computation. This stateless
  module evaluates eight exact rational metrics from one authorized aggregate fact ledger, preserves
  censored, missing, not-applicable, and unsupported states, and binds every result to the selected
  assay profile, controls, references, and compact M03-03 projection. That caller-declared projection
  proves internal content consistency, not independent M03-03 execution or issuer authenticity.
- `GLIO-PROTEOGEN-M03-05` — deterministic protein-inference artifact and contamination detection.
  This stateless module evaluates eight locked technical signals across six role-closed evidence
  unit kinds and emits categorical evidence scores, artifact states, contamination flags, and a
  retain/review/exclude mask. Its evidence scores are explicitly not calibrated probabilities.
- `GLIO-PROTEOGEN-M03-06` — deterministic protein-inference support harmonization. This stateless
  module applies eight exact lower-median fixed-point technical stages to retained support units,
  verifies held-out residual reduction plus direction, rank, and ambiguity invariants, and emits
  replayable transformations without abundance, probability, identity, or activity inference.
- `GLIO-PROTEOGEN-M03-07` — deterministic protein-inference support and abstention routing. This
  stateless module rederives compact M03-04/M03-06 receipts from their full strict results, then
  requires one reviewed envelope to admit the complete eight-dimension declaration without
  combining partial matches or inferring protein, proteoform, activity, or clinical meaning.
- `GLIO-PROTEOGEN-M03-08` — deterministic protein-inference provenance and release packaging.
  This stateless module closes genuine strict M03-01 through M03-07 results over eight exact
  caller artifacts, emits a canonical ten-member USTAR archive, and verifies externally supplied
  statements through an injected boundary without signing, key custody, or release authority.
- `GLIO-PROTEOGEN-M04-01` — deterministic proteoform/isoform protocol conformance. This stateless
  module closes a reviewed reference bundle, coordinate conventions, evidence eligibility,
  isoform discrimination, modification localization, quantification, and discordance handoff
  declaration without inferring proteoforms, discordance, activity, subtype, or treatment.
- `GLIO-PROTEOGEN-M04-02` — deterministic proteoform/isoform identity and lineage
  reconciliation. This stateless module closes genuine full M01-02 and M04-01 results over seven
  physical kinds, five opaque artifact roles, and one four-role assembly while retaining swaps,
  collisions, duplicates, cross-patient links, and non-observed evidence without identity repair
  or biological inference.
- `GLIO-PROTEOGEN-M04-03` — deterministic proteoform/isoform raw-manifest ingestion. This
  stateless module replays the exact full M04-02 result and validates four canonical manifest
  documents from immutable bytes while retaining typed diagnostics and never opening referenced
  scientific content, parsing measurement rows, executing models, or inferring biology.
- `GLIO-PROTEOGEN-M04-04` — deterministic proteoform/isoform quality metric computation. This
  stateless module replays the exact full M04-03 result and computes 32 fixed-point metrics from
  four caller-declared aggregate fact records under reviewed assay profiles. It never opens
  referenced content, authenticates measurements, executes models, or infers biology.
- `GLIO-PROTEOGEN-M04-05` — deterministic proteoform/isoform artifact and contamination
  detection. This stateless module replays the exact full M04-04 result, evaluates seven aggregate
  artifact classes under a version-and-configuration-bound profile, and emits only explicit
  categorical posteriors, triggered contamination flags, and excluded-only mask entries. Its ppm
  fractions are not calibrated probabilities, and missing or unsupported evidence abstains.
- `GLIO-PROTEOGEN-M04-06` — deterministic proteoform/isoform harmonization and normalization.
  This stateless module replays the exact full M04-05 result, applies eight reviewed fixed-point
  technical-factor stages to at most 32 retained support targets, and emits only a harmonized
analysis object plus an auditable transformation manifest. It preserves missingness, artifact
actions, support direction, rank, and composition without inferring abundance or biology.

- `GLIO-PROTEOGEN-M04-07` — deterministic unsupported-case and abstention routing. This
  stateless module replays exact full M04-04 and M04-06 results and routes one complete reviewed
  eight-dimension envelope to support or typed abstention with governed remediation. It never
  combines partial envelopes or emits an apparently valid scientific result for unsupported input.

The published module slices and the M04-07 release candidate expose strict JSON Schema
2020-12 contracts through HTTP and command-line schema routes, plus typed library and
module-specific command boundaries. M01-01 and M01-02 additionally provide deterministic
append-only event-chain verification. The database hash chains are integrity evidence, not
signatures or standalone external trust anchors. M01-02 accepts
only scoped opaque identity tokens and privacy-minimized concordance summaries; raw direct
identifiers, genotypes, reads, and molecular measurements are outside its public and persisted
outputs.

## Development

```bash
uv sync
uv run ruff check .
uv run mypy src
uv run pytest
uv run python tools/verify_module_validation.py
uv run python tools/verify_module_validation.py --run-evaluators --evaluator-timeout-seconds 300
uv run python -m evals.m01_01.run
uv run python -m evals.m01_02.run
uv run python -m evals.m01_03.run
uv run python -m evals.m01_04.run
uv run python -m evals.m01_05.run
uv run python -m evals.m01_06.run
uv run python -m evals.m01_07.run
uv run python -m evals.m01_08.run
uv run python -m evals.m02_01.run
uv run python -m evals.m02_02.run
uv run python -m evals.m02_03.run
uv run python -m evals.m02_04.run
uv run python -m evals.m02_05.run
uv run python -m evals.m02_06.run
uv run python -m evals.m02_07.run
uv run python -m evals.m02_08.run
uv run python -m evals.m03_01.run
uv run python -m evals.m03_02.run
uv run python -m evals.m03_03.run
uv run python -m evals.m03_04.run
uv run python -m evals.m03_05.run
uv run python -m evals.m03_06.run
uv run python -m evals.m03_07.run
uv run python -m evals.m03_08.run
uv run python -m evals.m04_01.run
uv run python -m evals.m04_02.run
uv run python -m evals.m04_03.run
uv run python -m evals.m04_04.run
uv run python -m evals.m04_05.run
uv run python -m evals.m04_06.run
uv run pytest benchmarks/m01_01_validation.py --benchmark-only --no-cov
uv run pytest benchmarks/m01_02_identity_lineage.py --benchmark-only --no-cov
uv run pytest benchmarks/m01_03_ingestion.py --benchmark-only --no-cov
uv run pytest benchmarks/m01_04_quality_metrics.py --benchmark-only --no-cov
uv run pytest benchmarks/m01_05_artifact_detection.py --benchmark-only --no-cov
uv run pytest benchmarks/m01_06_harmonization.py --benchmark-only --no-cov
uv run pytest benchmarks/m01_07_support_routing.py --benchmark-only --no-cov
uv run pytest benchmarks/m01_08_release_packaging.py --benchmark-only --no-cov
uv run pytest benchmarks/m02_01_metadata_validation.py --benchmark-only --no-cov
uv run pytest benchmarks/m02_02_identity_bindings.py --benchmark-only --no-cov
uv run pytest benchmarks/m02_03_identification_ingestion.py --benchmark-only --no-cov
uv run pytest benchmarks/m02_04_quality_metrics.py --benchmark-only --no-cov
uv run pytest benchmarks/m02_05_artifact_detection.py --benchmark-only --no-cov
uv run pytest benchmarks/m02_06_harmonization.py --benchmark-only --no-cov
uv run pytest benchmarks/m02_07_support_router.py --benchmark-only --no-cov
uv run pytest benchmarks/m02_08_release_packaging.py --benchmark-only --no-cov
uv run pytest benchmarks/m03_01_protocol_metadata.py --benchmark-only --no-cov
uv run python -m evals.m03_02.benchmark
uv run python -m evals.m03_03.benchmark
uv run python -m evals.m03_04.benchmark
uv run python -m evals.m03_05.benchmark
uv run python -m evals.m03_06.benchmark
uv run python -m evals.m03_07.benchmark
uv run python -m evals.m03_08.benchmark
uv run python -m evals.m04_01.benchmark
uv run python -m evals.m04_02.benchmark
uv run python -m evals.m04_03.benchmark
uv run python -m evals.m04_04.benchmark
uv run python -m evals.m04_05.benchmark
uv run python -m evals.m04_06.benchmark
uv run python -m tools.scan_secrets
```

The `glio-proteogen` command exports each module's contracts and exposes M01-01 register,
evaluate, retrieve, and ledger-verification operations plus M01-02 reconcile, retrieve, and
ledger-verification operations, M01-03 bounded file inspection, M01-04 quality computation,
M01-05 artifact detection, M01-06 technical harmonization, M01-07 support routing, M01-08
directory-backed release package build and verification, and M02-01 peptide-identification
metadata conformance, M02-02 immutable identity-binding audit, and M02-03 directory-backed
identification raw-input ingestion, M02-04 stateless identification-quality computation, M02-05
stateless identification-artifact detection, M02-06 identification harmonization, M02-07
identification support routing, and M02-08 directory-backed identification release packaging and
verification, plus M03-01 stateless protein-inference protocol conformance and M03-02 stateless
protein-inference artifact identity-lineage reconciliation, plus M03-03 bounded, directory-backed
protein-inference raw-source admission, M03-04 metadata-only quality computation, M03-05
categorical artifact detection over an authorized evidence ledger, and M03-06 fixed-point support
harmonization, M03-07 protein-inference support and abstention routing, M03-08 local,
directory-backed protein-inference release packaging and verification, and M04-01 stateless
proteoform/isoform protocol conformance, M04-02 stateless proteoform/isoform identity and lineage
reconciliation, M04-03 directory-backed raw-manifest ingestion, and M04-04 metadata-only fixed-point
quality metric computation, M04-05 aggregate artifact and contamination detection, and M04-06
fixed-point support harmonization and normalization.
For example:

```bash
glio-proteogen export-schema protocol-schema
glio-proteogen identity export-schema request
glio-proteogen identity reconcile request.json --database evidence.sqlite3
glio-proteogen identity verify-ledger --database evidence.sqlite3
glio-proteogen raw export-schema request
glio-proteogen raw inspect variants.vcf --source-id source.variants
glio-proteogen quality export-schema request
glio-proteogen quality compute quality-request.json
glio-proteogen artifact export-schema request
glio-proteogen artifact detect artifact-request.json
glio-proteogen harmonize export-schema request
glio-proteogen harmonize run harmonization-request.json
glio-proteogen support export-schema request
glio-proteogen support route support-request.json
glio-proteogen release export-schema request
glio-proteogen release build release-request.json release-source --output release.tar
glio-proteogen release verify release-result.json release.tar
glio-proteogen identification export-schema request
glio-proteogen identification validate-metadata conformance-request.json
glio-proteogen binding export-schema request
glio-proteogen binding audit identity-binding-request.json
glio-proteogen identification-raw export-schema request
glio-proteogen identification-raw ingest ingestion-request.json source-directory
glio-proteogen identification-quality export-schema request
glio-proteogen identification-quality compute identification-quality-request.json
glio-proteogen identification-artifacts export-schema request
glio-proteogen identification-artifacts detect identification-artifact-request.json
glio-proteogen identification-harmonization export-schema request
glio-proteogen identification-harmonization harmonize identification-harmonization-request.json
glio-proteogen identification-support export-schema request
glio-proteogen identification-support route identification-support-request.json
glio-proteogen identification-release export-schema request
glio-proteogen identification-release build identification-release-request.json release-source --output identification-release.tar
glio-proteogen identification-release verify identification-release-result.json identification-release.tar
glio-proteogen protein-inference-protocol export-schema request
glio-proteogen protein-inference-protocol validate protein-inference-protocol-request.json
glio-proteogen protein-inference-lineage export-schema request
glio-proteogen protein-inference-lineage reconcile protein-inference-lineage-request.json
glio-proteogen protein-inference-raw export-schema request
glio-proteogen protein-inference-raw ingest protein-inference-raw-request.json source-directory
glio-proteogen protein-inference-quality export-schema request
glio-proteogen protein-inference-quality compute protein-inference-quality-request.json
glio-proteogen protein-inference-artifacts export-schema request
glio-proteogen protein-inference-artifacts detect protein-inference-artifact-request.json
glio-proteogen protein-inference-harmonization export-schema request
glio-proteogen protein-inference-harmonization harmonize protein-inference-harmonization-request.json
glio-proteogen protein-inference-support export-schema request
glio-proteogen protein-inference-support route protein-inference-support-request.json
glio-proteogen protein-inference-release export-schema request
glio-proteogen protein-inference-release build protein-inference-release-request.json release-source --output protein-inference-release.tar
glio-proteogen protein-inference-release verify protein-inference-release-result.json protein-inference-release.tar
glio-proteogen proteoform-protocol export-schema request
glio-proteogen proteoform-protocol validate proteoform-protocol-request.json
glio-proteogen proteoform-lineage export-schema request
glio-proteogen proteoform-lineage reconcile proteoform-lineage-request.json
glio-proteogen proteoform-raw export-schema request
glio-proteogen proteoform-raw ingest proteoform-raw-request.json proteoform-raw-source --output proteoform-raw-result.json
glio-proteogen proteoform-quality export-schema request
glio-proteogen proteoform-quality compute proteoform-quality-request.json --output proteoform-quality-result.json
glio-proteogen proteoform-harmonization export-schema request
glio-proteogen proteoform-harmonization harmonize proteoform-harmonization-request.json
glio-proteogen proteoform-support export-schema request
glio-proteogen proteoform-support route proteoform-support-request.json
```

`glio-proteogen serve` provides the strict byte-validated HTTP operations and all module schema
routes. M01-08 intentionally keeps artifact bytes at its library and directory-backed CLI boundary;
it does not invent an HTTP upload protocol. M01-03 inspection, M01-04 quality computation, M01-05
artifact detection, M01-06 harmonization, M01-07 support routing, M01-08 release packaging, and
M02-01 metadata conformance are stateless. M01-08 publishes package bytes only for a released
result; quarantined results remain metadata-only. M02-02 is also stateless and consumes only an
already-issued M01-02 resolution plus opaque content-addressed binding claims.
M02-03 is also stateless: byte content stays at the library or safe directory-backed CLI
boundary, while its result contains only digests, format metadata, and typed diagnostics.
M02-04 is stateless and consumes only authorized aggregate observations and fixed thresholds;
it emits a typed quality profile and does not retain raw spectra, PSMs, or biological claims.
M02-05 is stateless and consumes only authorized aggregate identification-QC signals plus a pinned
profile, policy, and explicit rules. It emits typed technical flags and a target-level exclusion
mask; it does not parse raw assay inputs, repair measurements, infer protein subtypes, or retain
raw spectra or peptide rows.
M02-06 is stateless and consumes only the exact M02-01 through M02-05 receipts plus typed aggregate
abundance observations. It emits a harmonized analysis object and auditable eight-stage
transformation manifest; it does not parse assay files, impute missing evidence, alter upstream
artifacts, or make subtype, kinase-state, treatment, or clinical claims.
M02-07 is stateless and consumes only compact, digest-bound M02-04/M02-06 receipts plus reviewed
support envelopes and typed declarations. It emits support-domain assessments, abstention reasons,
and reviewed remediation codes; it does not copy harmonized values, combine partial envelope
matches, infer biology, or make treatment or clinical claims.
M02-08 is stateless and closes exact, separately supplied M02-01 through M02-07 JSON result bytes
against their typed objects, artifact declarations, issued digests, dispositions, lineage receipts,
and cross-stage identity bindings. Its manifest is signed without including the generated signature
verification receipt, avoiding a circular statement. The HTTP surface is schema-only. The CLI has
no built-in verifier: a build therefore returns typed quarantine metadata and writes no archive,
while verification can establish canonical structure and content but not authenticity. Positive
release remains a library/service/plugin operation with an explicitly injected verifier. M02-08
does not inspect the parent subtype artifact for biological meaning, own signing keys, authenticate
release authority, infer kinase state, fuse omics, or make treatment or clinical claims.
M03-01 is stateless and validates only a caller-declared, content-bound protein-inference protocol
and reviewed profile. Its conformance receipt preserves search-space-relative uniqueness,
shared/razor evidence restrictions, indistinguishable group members, and the exact downstream
handoff semantics. It does not authenticate issuers or references, inspect observations, run
protein inference, estimate false-discovery rates, infer complex activity, or make treatment or
clinical claims.
M03-02 is stateless and consumes exact, self-validating M01-02 and M03-01 results plus opaque,
content-addressed artifact claims, a reviewed lineage policy, and categorical copy-number
concordance receipts. It preserves the physical lineage graph separately from the artifact DAG,
quarantines swaps, collisions, duplicate assignments, cross-patient propagation, and producer
drift, and abstains when governed upstream identity or concordance evidence is unresolved. It does
not repair or infer identity, inspect peptide sequences or protein accessions, consume raw
copy-number or abundance values, infer proteins or complexes, score activity, fuse omics, or make
treatment or clinical claims.
M03-03 is stateless and binds genuine M01-02, M03-01, and M03-02 receipts to one bounded,
content-addressed raw-source capsule. Its library surface consumes bytes or read-once streams; its
CLI maps exact safe source identifiers to regular non-reparse files beneath one directory. The HTTP
surface exports schemas only and deliberately has no raw-ingestion POST route. It validates
transport, decompression, structural references, search-space/PTM closure, and build/CV/unit
coherence without retaining source bytes, assigning peptides, inferring proteins or complexes,
scoring activity, or making treatment or clinical claims.
M03-04 is stateless and consumes one authorization-checked, caller-declared compact M03-03 receipt,
one aggregate fact ledger, and one reviewed assay-quality policy. It computes exact integer-rational
source completeness, peptide assignment, ambiguity, proteoform discrimination, detection support,
competition closure, control recovery, and sample-context coherence metrics while retaining typed
unresolved states. The compact receipt and ledger establish self-consistency under their digests;
they do not independently attest that M03-03 executed or authenticate an issuer. M03-04 does not
parse raw sources, traverse peptide rows, redo protein inference, score complex activity, infer a
proteotype, or make treatment or clinical claims.
M03-05 is stateless and consumes one authorization-checked compact M03-04 quality receipt, one
content-addressed role-compatible artifact ledger, and one reviewed detector policy. It reduces
exact integer supporting/evaluated counts into categorical evidence scores and technical masks;
it does not parse raw sources, assign proteins, estimate calibrated probabilities, score complex
activity, authenticate an external issuer, or make treatment or clinical claims.
M03-06 is stateless and consumes the exact compact M03-05 artifact projection plus a bounded,
content-addressed support ledger and reviewed eight-stage profile. It derives signed lower-median
fixed-point shifts, applies them sequentially only to retained observed units, and replays held-out
technical residuals plus direction, rank, and ambiguity-fraction invariants. It preserves typed
missingness and the artifact firewall; it does not estimate abundance or calibrated probability,
infer protein, proteoform, complex activity, or kinase state, authenticate an external issuer, or
make treatment or clinical claims.
M03-07 is stateless and consumes full strict M03-04 and M03-06 results alongside compact receipts
rederived from those exact results solely to prove projection closure. It routes the complete
assay, specimen, disease-class, quality, completeness, platform, reference, and intended-use
declaration against one reviewed joint envelope, preserving missing/unknown states and emitting
only support or typed abstention with governed remediation. It does not reinterpret or mutate
upstream results, combine partial envelopes, infer protein, proteoform, complex activity, or kinase
state, authenticate an external issuer, or make treatment or clinical claims.
M03-08 is stateless and consumes exact canonical bytes plus separately supplied strict full
M03-01 through M03-07 result objects. It closes stage identity, predecessor, quality, artifact,
harmonization, support, intended-use, and parent bindings before signature verification; then it
emits eight caller members plus one generated manifest and one verification receipt in canonical
USTAR form. The result contract rederives descriptor byte size, while the verify API establishes
descriptor digest/content equality and authenticity against supplied bytes. M03-08 does not sign,
hold keys, authenticate a signer, establish release authority, mutate upstream evidence, infer
protein or activity, or make treatment or clinical claims.
M04-01 is stateless and validates one content-bound proteoform/isoform protocol declaration against
one reviewed conformance profile. It preserves exact reference, coordinate, eligibility,
discrimination, localization, quantification, unresolved-state, and protein-RNA-discordance
handoff semantics. It does not inspect assay observations, infer proteoforms or discordance,
localize modifications, fuse omics, score kinase activity, emit subtypes, or recommend treatment.
M04-02 is stateless and consumes exact full M01-02 and M04-01 results plus opaque, role-compatible
artifact claims and one reviewed derivation policy. It preserves the seven-kind physical lineage
separately from the five-role artifact graph, retains duplicate content, and quarantines swaps,
collisions, cross-patient links, and producer drift while abstaining on non-observed evidence. It
does not repair or infer identity, inspect artifact bytes, execute CN-to-protein regression, infer
protein, proteoform, discordance, or kinase state, fuse omics, or make treatment or clinical claims.
M04-03 is stateless and consumes the exact full M04-02 result plus a reviewed parser policy, four
artifact declarations, and an exact built-in mapping of four roles to immutable canonical JSON
bytes. It validates only typed manifest metadata and retains content references without opening
external scientific artifacts. Its HTTP surface exports schemas only; its CLI snapshots exactly
four regular non-reparse files and atomically creates a new result without rereading sources or
overwriting output. It does not parse spectra or scientific rows, compute quality metrics, execute
models, mutate inputs, infer negatives, or make identity, protein, proteoform, PTM, discordance,
kinase, subtype, treatment, or clinical claims.
M04-04 is stateless and consumes the exact full M04-03 result plus a reviewed quality policy and,
for validated upstream input, one sealed four-role aggregate fact ledger. It computes eight exact
integer ppm metrics per role with deterministic threshold semantics, retains censoring and missing
states, and emits typed findings without opening any referenced scientific content. Its HTTP and
CLI boundaries are metadata-only and strict. It does not authenticate caller-declared aggregates,
identify proteins, proteoforms, isoforms, or PTMs, localize modifications, compute protein-RNA
discordance, execute a model, or make treatment or clinical claims.
M04-07 is stateless and consumes exact full M04-04 and M04-06 results alongside compact receipts
rederived solely to prove projection closure. It evaluates assay, specimen, disease class, quality,
completeness, platform, reference, and intended use against one complete reviewed joint envelope.
Missing, unknown, outside-domain, unreleasable, extra-member, and cross-envelope inputs emit only a
typed abstention reason and governed remediation path; partial envelopes are never combined.
M04-07 does not reinterpret upstream science, emit protein-RNA discordance or any apparently valid
scientific result for unsupported input, infer identity or biology, or make treatment claims.

All research-facing outputs are research-use-only until their module-specific evidence gate
is independently satisfied. CI and release workflows assemble reproducible candidate evidence;
they never issue reviewer approval or qualify a module.
