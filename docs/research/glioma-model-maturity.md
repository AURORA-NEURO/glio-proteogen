# Glioma model maturity and replacement queue

This inventory separates executable scientific inference from contract, lineage,
workflow, and release plumbing. A package being `0.1.0-provisional` does not by
itself mean that it contains a fake model, and a passing schema or replay test
does not make a numerical method scientifically mature.

## Implemented research inference

The mounted additive research namespace currently contains fourteen distinct,
independently testable scientific-inference lanes plus one integrated
composition surface. Distinctness in the fourteen-lane mounted inventory means
separate algorithms and receipts, not scientifically independent evidence:

- `glio-ecgi/1.0.0`: directed robust evidence-graph inference with censored
  observations, complex bottlenecks, kinase permutations, bootstrap uncertainty,
  and ablations;
- `gbm-proteomic-axes/1.0.0`: an exact runtime port of seven published GBM
  protein-abundance XGBoost ensembles, locked to the author implementation and
  all 28 supplied output oracles; and
- `gbm-rna-tumor-purity/1.0.0`: an exact NumPy runtime port of the published
  5,829→32→16→1 GBMPurity bulk-RNA model, with fail-closed source conversion,
  the published 80% gene-overlap gate, source-parity preprocessing, output
  clipping, exact active-ReLU local decomposition, and replay. The source
  provides one fitted network, so the lane explicitly declines to manufacture
  an uncertainty interval; and
- `gbm-rna-composition/0.1.0`: a caller-owned, count-native
  Dirichlet--multinomial adaptive-unknown simplex fit over positive GBM lineage
  signatures. It reports known RNA mixture weights, unexplained mass, KKT and
  objective-trace diagnostics, condition number, and threshold-free OOD
  diagnostics with exact replay. It is mounted as a limited research lane;
  no GBmap artifact is bundled and weights are never called cell fractions; and
- `neftel-bulk-protein-programs/1.0.0`: a separately identified robust
  bulk-protein evidence model over the exact Neftel Table S2 marker identities
  and ranks; and
- `gbm-microenvironment-graph/1.0.0`: a source-locked Neftel-to-ECGI bridge
  that projects only supported mesenchymal-like and oligodendrocyte-progenitor-
  like bulk-protein evidence into a signed GBM microenvironment graph. It
  preserves missing families as missing, propagates uncertainty through the
  directed graph, and explicitly does not estimate cell fractions or clinical
  states. It may carry independently digested Winter hypoxia and Verhaak
  mesenchymal proteomic-axis scores as secondary observations. Their measurement
  intervals are bounded by a profile-locked 0.35 standard-error floor before
  graph projection so model-score precision is not mistaken for cross-engine
  calibration; and
- `sphinks-gbm-master-kinase-concordance/1.0.0`: an independently authored,
  source-locked phosphosite concordance model over the 24 subtype-specific
  master-kinase signatures published by Migliozzi et al., with robust one-sided
  estimation, residue-stratified competitive nulls, fixed-family FDR,
  uncertainty, support gates, and ablations.
- `migliozzi-gbm-functional-proteotype/1.0.0`: a source-locked joint robust fit
  of relative GPM, MTC, NEU, and PPR bulk-protein concordance coordinates over
  the exact 600 Table 2d genes, with one-sided censoring, an independent
  source-rank-stratified four-axis permutation/BH family, deterministic
  bootstrap intervals, and refit ablations. Table 2e rows remain source-cohort
  context and never become sample pathway or categorical subtype calls.
- `kncc-gbm-longitudinal-concordance/1.0.0`: a source-locked protein-transition
  model fitted from 104 strict PDC000514 primary/recurrent GBM pairs, with honest
  patient-grouped nested cross-validation, bound-aware robust inference,
  coupled measurement/coefficient uncertainty, source-processing and driver
  ablations, and exact heteroscedastic-Huber PELT segmentation.
- `kncc-paired-phosphosite-transition/1.0.0`: a source-locked phosphosite
  transition model fitted from 88 strict PDC000515 primary/recurrent GBM pairs,
  with nested grouped evaluation, exact full-refit bootstrap perturbations,
  composite-site preservation, assay attestation, uncertainty decomposition,
  support suppression, and fail-closed maturity gates; and
- `kncc-gbm-longitudinal-kinase-transition/1.0.0`: a source-locked comparison of
  PDC000515 longitudinal phosphosite transitions with the fixed 24-hypothesis
  SPHINKS signature family. It uses training-only grouped evaluation,
  residue/cardinality-stratified competitive nulls, fixed-family BH FDR,
  inverse-multiplicity correction, composite preservation, and patient-bootstrap
  uncertainty. It is signature concordance only, remains LIMITED, and is not
  biochemical/causal kinase activity or evidence independent of PDC000515; and
- `kncc-reactome-conditional-transition/1.0.0`: a fitted global-plus-conditional
  protein-transition model over a fixed, repository-authored 10-event Reactome
  V97 glioma panel and 104 strict PDC000514 pairs. It uses training-only robust
  source effects, eight held-patient folds, five held-gene folds, degree-aware
  global residualization, bound-aware ridge IRLS, 256 patient-bootstrap source
  fits, request-specific reconstruction gates, and structural ablations. Its
  output is membership concordance rather than pathway activation or flux, and
  overlap-confounded PI3K/AKT evidence can never be fully supported.
- `kncc-reactome-complex-transition/1.0.0`: 28 separately fitted,
  missing-aware robust rank-one protein-transition factors over exact Reactome
  V97 participant sets in 11 repository-authored pilot domains. The panel was
  informed by public glioma biology and the PDC000514 source paper and selected
  without reading abundance arrays during import; it is not demonstrated
  outcome-independent. The model uses 104 strict
  PDC000514 pairs, eight patient-grouped held-member evaluation folds, 128
  patient-bootstrap source fits, censor-aware runtime projection, and explicit
  source-processing, loading, member, and overlap ablations. Its output is
  participant-set transition concordance, not assembly, activity,
  essentiality, stoichiometry, causality, or clinical prediction.
- `kncc-neftel-program-transition/1.0.0`: a fitted global-plus-conditional
  protein-transition model over the exact eight Neftel Table S2 program marker
  sets and 104 strict PDC000514 primary/recurrent GBM pairs. It uses
  patient-grouped outer folds, held-marker evaluation, deterministic Huber
  IRLS/ridge inference, 128 patient-bootstrap refits, one-sided censoring, and
  measurement/source/topology ablations. Its fitted dictionary beats the
  global-only comparator but loses to equal marker membership, so every
  numerical runtime coordinate is capped `LIMITED`. It is bulk-protein
  same-cohort transition concordance, not single-cell state, cellular fraction,
  recurrence prediction, tumor evolution, or clinical evidence.

- `m1403-glioma-microenvironment-programs/0.1.0-provisional`: a typed,
  research-only microenvironment program graph over mesenchymal, myeloid,
  T-cell, endothelial, hypoxia, angiogenic, and OPC-like programs. It uses
  robust Huber signed coordinate descent, explicit missing/unsupported and
  left-censored evidence states, deterministic bootstrap intervals, and
  signed program relations. The historical categorical feature constructor is
  retained only as a compatibility path; the typed lane is synthetic and does
  not claim cell fractions, diagnosis, prognosis, or treatment response.
- `m1405-glioma-temporal-programs/0.1.0-provisional`: a typed temporal lane
  that fits robust, Huber-smoothed RTK/PI3K/AKT/mTOR, p53/cell-cycle, IDH/HIF1A,
  mesenchymal, and proliferation trajectories with left-censored evidence,
  deterministic bootstrap intervals, and interval-supported change points.
  Missing and unsupported observations are excluded and an all-unsupported
  history abstains; the original ordered metadata replay remains compatibility-
  only and no trajectory is diagnostic, prognostic, or prescriptive.

The provisional M11-05 longitudinal module now also has an additive typed
proteomic-effect lane. It fits subject-level recurrence trajectories with
quality/standard-error weighted Huber IRLS with midpoint-median MAD scaling,
preserves left-censored and unsupported states, and detects molecular change
points from robust loss reduction rather than caller relabeling. The legacy
opaque-reference path is unchanged and remains provisional; this lane is an
evolutionary evidence signal, not a validated tumor-evolution or treatment-
response predictor. A
left-censored point with no assay error now inherits the within-history median
observed standard error (using the midpoint average for an even sample), so
its one-sided contribution has an evidence-derived scale. A history containing
only censored points without any uncertainty basis abstains rather than
assigning an arbitrary precision.

The trajectory location starts from observed effects only, projects onto exact
censor bounds, and never shifts a detection limit into a surrogate effect.

The additional `glio-ecgi-kncc-gbm-transition/1.0.0` factor-graph surface is not
a fifteenth mounted model. It runs the exact PDC000514 Reactome and
PDC000515 SPHINKS signature-transition child engines numerically independently
but deterministically in serial, nests their exact receipts, and adds only a
locked 41-node presentation topology with 39 annotation-only containment edges
and zero numerical cross-block edges. It performs no cross-modal fusion or
feedback and therefore does not increase the fourteen-lane independent-inference
count. See
[`kncc-gbm-factor-graph.md`](kncc-gbm-factor-graph.md).

Two exact-source CPTAC GBM implementations are tracked separately from that
mounted inventory: `cptac-gbm-cis-dosage/1.0.0` and
`cptac-gbm-transcript-protein-discordance/1.0.0`. Both provide real local
fit/query/replay algorithms over caller-owned exact source copies, but neither
bundles a fitted artifact or mounts an HTTP route. A caller-built artifact is
therefore local cohort evidence, not a repository-shipped model, and neither
implementation increases the fourteen-lane mounted count.

These lanes remain research-only. Their presence does not promote any governed
module or establish clinical validity.

## Published GBM RNA-purity replacement

The additive `gbm-rna-tumor-purity/1.0.0` lane now replaces caller-declared or
hash-derived purity-like behavior with the exact fitted GBMPurity neural model
for its narrow intended population. It consumes raw bulk RNA counts, not
protein evidence, and emits one malignant-cell-fraction estimate—not immune
composition. Exact PyTorch/NumPy parity, source-tree admission, coverage gates,
local numerical attribution, API/CLI replay, and claim ceilings are documented
in [`gbm-rna-purity.md`](gbm-rna-purity.md).

This does not complete M14 cellular microenvironment replacement. A licensed,
donor-aware GBM single-cell reference and count-native mixture model are still
required for multi-lineage fractions.

The fixed CC BY 4.0 GBmap Zenodo artifact is now conditionally admitted as the
preferred offline fitting source. Its approximately 9 GB source bytes have not
been downloaded, SHA-256 hashed, or fitted in this checkout. A source-independent
core now implements exact pseudobulk aggregation, fold-local stable-marker
selection, leakage-safe whole-study and within-study donor validation plans,
donor/study-shrunk Dirichlet-multinomial fitting, adaptive-unknown simplex
inference, calibrated mismatch diagnostics, and an end-to-end training-only
candidate-selection protocol with equal validation-family weighting. Its fail-closed
development profile records `fit_state="development_unfitted"`, binds those
semantics, and forbids model, artifact, runtime, HTTP, CLI, and `SUPPORTED`
availability. The 109-versus-110 conflict is now source-locked: final Table S1,
all CELLxGENE versions, and the original preprint support 110 source donor
categories, while only the final paper prose says 109. A byte-range audit of
the authoritative Zenodo H5AD additionally found 113 raw patient categories and
17 raw author batches. The offline extractor now locks the legacy HDF5/CSR
layout, exact 20-label vocabulary, a 17→16 study crosswalk, two-pass file
integrity, checked count aggregation, and deidentified receipts. It refuses to
fit unless the digest-bound 113→110 donor crosswalk is supplied. That crosswalk
now groups the three source PW032 samples to PW032 and, from the original Pombo
patient table and reporting summary, groups the distinct `R4` and `R4 n.c.`
source samples to donor R4. Raw categories are never treated as independent
donors merely to make training proceed. Exact source SHA-256 verification,
extraction, fitting, and held-out calibration remain. The redistribution
boundary, validation gates, and remaining blockers are recorded in
[`gbmap-deconvolution-source-admission.md`](gbmap-deconvolution-source-admission.md).
No fitted GBmap artifact is bundled, so the source-admission candidate remains
unfitted. The separate caller-owned `gbm-rna-composition/0.1.0` runtime is now
mounted at `/v1/research/gbm-rna-composition` and exposed by the matching CLI;
it increases the fourteen-lane inventory without making a source-derived GBmap
claim.

The source-independent core also exposes an explicitly named
`gbm-rna-composition/0.1.0` caller-owned runtime. It accepts a complete count
vector and positive reference signatures, solves the adaptive-unknown
Dirichlet--multinomial simplex objective, reports KKT/objective-trace closure
and threshold-free OOD diagnostics, and supports deterministic replay. This is
a limited RNA-mixture coordinate only: unknown mass is retained, lineage
weights are never relabelled as histologic cell fractions, and no GBmap
artifact or patient data are bundled. The development GBmap profile therefore
remains `development_unfitted` with no source-derived `SUPPORTED` claim; the
mounted route is explicitly caller-owned and limited.

## Local M07 cis-dosage substitution boundary

`m07-cptac-gbm-cis-dosage-cohort-evidence/1.0.0` now provides an exact local
facade over the fitted `cptac-gbm-cis-dosage/1.0.0` lane. It identifies only
M07-04's scalar-copy/interval-midpoint declaration proxy as eligible for
cohort-evidence substitution. The delegate is a genuine fold-local Huber-IRLS
CNV-to-RNA-to-protein model over exact CPTAC GBM sources, but it remains a
gene-level cohort query rather than a patient posterior or causal mediation
model. Unverified supplement redistribution terms require a same-user local
artifact and structurally forbid a public HTTP mount. M07-05 mechanism
integration and M07-06 uncertainty decomposition remain out of scope. See
[`m07-cis-dosage-facade.md`](m07-cis-dosage-facade.md).

The M07-04 mechanism-guided dosage runtime now coalesces repeated observations
of one locus into a shared-latent Huber--IRLS posterior. Technical repeats are
precision-weighted with robust down-weighting, one posterior row is emitted per
feature, and mixed units or incompatible feature families abstain before any
numeric claim. Source digests are deduplicated in the resulting evidence ledger;
the legacy contract, optimizer identifiers, and replay boundary remain intact.

## Source-locked phosphosite runtime lane

`kncc-paired-phosphosite-transition/1.0.0` is now fitted from 88 strict
PDC000515 primary/recurrent pairs as a separately source-locked phosphosite
concordance axis. It preserves composite site groups, technical repeats,
missingness, nested patient-grouped evaluation, bootstrap uncertainty, and an
exact SPHINKS peptide/site crosswalk. It is packaged, integrity checked, and
mounted as a stateless API/CLI/workbench lane with exact replay. Protein
adjustment, occupancy, kinase inference, and cross-assay fusion remain
explicitly `not_fitted`; see
[`longitudinal-gbm-phosphosite-foundation.md`](longitudinal-gbm-phosphosite-foundation.md).

## Source-locked signature-transition lane

`kncc-gbm-longitudinal-kinase-transition/1.0.0` is mounted as an additive
API/CLI lane, not as a replacement for the raw-phosphosite axis. Its fully
training-only five-fold held-pair evaluation recovered 68/88 directions versus
70/88 for the raw phosphosite comparator on the same folds. Signature-only and
raw-only correct counts were 7 and 9 (exact McNemar `p=.804`), so it does not add
independent evidence. Eleven of 12 selected signatures pass the frozen
bootstrap selection threshold; CHEK2 is explicitly unstable. Full-set bootstrap
stability and interval-calibration gates fail, forcing every estimable runtime
output to LIMITED. See
[`longitudinal-gbm-kinase-transition.md`](longitudinal-gbm-kinase-transition.md).

## Compatibility facades, not new inference lanes

Five API-only v2 facades expose existing fitted research evidence at explicit
module integration boundaries:

- the M09 complex-transition facade delegates participant-set transition
  scoring, uncertainty, ablations, and replay to the fitted PDC000514/Reactome
  factor lane, replacing only participant-transition numerical stand-ins and
  never emitting assembly, stoichiometry, essentiality, or activity;
- the M10 functional-proteotype facade delegates numerical scoring, uncertainty,
  ablations, and replay to the source-locked Migliozzi four-axis bulk-protein
  model, replacing only synthetic or caller-declared numerical stand-ins as
  research evidence;
- the M11 protein-native subtype facade delegates numerical scoring and replay
  to the exact published GBM proteomic-axis lane; and
- the M14 microenvironment protein-program facade delegates numerical scoring
  and replay to the Neftel bulk-protein program lane.
- the M15 longitudinal-recurrence facade delegates transition scoring,
  uncertainty, ablations, optional change-point analysis, and replay to the
  fitted KNCC/PDC000514 longitudinal protein model.

They add responsibility/exclusion metadata and compatibility transport, not new
scientific models, posterior subtype/cell-fraction estimates, or independent
evidence. They therefore do not increase the fourteen-lane inference count.

## Strict numerical-stand-in floor

At the 2026-08-29 source snapshot, M06 through M20 contain 120 provisional
packages. M06 through M15 contain 80 packages. An exhaustive static audit of
those 80 identifies 22 engines with unmistakable numerical stand-ins:

```text
M06-04
M07-04 M07-05
M08-03 M08-04 M08-05
M09-03 M09-05 M09-06
M10-03 M10-07
M11-05 (legacy opaque path)
M11-06
M13-03 M13-05 M13-06
M14-03 M14-05
```

The strict union contains nine digest-derived-number engines, six fixed-posterior
engines, three mean or weighted-blend engines, four declaration/no-model
scientific engines, and one sine-wave fixture estimator; categories overlap.
Examples include SHA-256 bytes used as a complex or pathway score, fixed
posterior intervals, caller-declared state returned with posterior mass `1.0`,
and M10-03's `sin(index + 1) * 0.1` fixture with fixed `0.95` support and a
fixed-width interval. M11-06 hashes an upstream digest and declared perturbation
into a response with a fixed uncertainty envelope. M11-05 is listed only for
its backward-compatible opaque path; typed effect requests use the robust
trajectory implementation described above and are not counted as a fixed
posterior estimator.

The strict 20 are a floor for counterfeit estimators, not the whole scientific
debt inventory. M12-06's legacy scalar compatibility path remains in this
floor, while its new typed glioma replicate lane is a real robust estimator.
M06-04, M07-05, M08-03, M09-03, M09-04, M09-05, M09-06, M10-04, M10-05, M11-03, M11-04, M12-03, M12-04, M12-06, M13-04, M15-04, and M15-05 now have typed glioma
research lanes documented below while their legacy paths remain provisional.
Three representation constructors—M07-02, M08-02, and
M09-02—also synthesize numeric vectors from hashes. They remain classified as
representation plumbing, but their vectors must never be described as learned
biological features. The exhaustive partition is therefore 20 strict stand-ins,
0 transparent scientific shells, three synthetic representation constructors,
and 55 schema, safe-abstention, validation, registry, evidence-publisher, or
other non-estimator engines.

The strict list deliberately excludes representation/schema plumbing, safe
abstention, lineage services, and M16 through M20 workflow duties. Those
surfaces may be scientifically incomplete without being counterfeit
estimators. The broader partition above keeps synthetic representations visible
without relabelling workflow metadata as biological inference.

Governed contracts and digests are preserved while replacements are developed as
new research lanes. A provisional route must not be silently relabeled as mature
or redirected to a different algorithm.

## Completed replacement

The first priority is now implemented as the additive KNCC research lane. It
does not alter or silently redirect the frozen governed longitudinal contracts.
Its output is deliberately named source-cohort protein concordance rather than
tumor evolution, and its nested held-pair performance is internal source-cohort
evaluation rather than external validation.

The M10 functional-proteotype scientific replacement is also implemented as the
additive `migliozzi-gbm-functional-proteotype/1.0.0` lane. It uses exact licensed
aggregate Table 2d/2e evidence and a real constrained estimator rather than the
governed M10-03 sine-wave fixture or M10-07 digest-derived score. The governed
M10 routes, schemas, digests, and placeholder implementations remain visible
technical debt and are not silently redirected or relabeled as mature. The
research/v2 M10 compatibility facade now exposes the fitted model at the module
boundary with explicit per-responsibility exclusions; it is not a governed
replacement and does not convert concordance coordinates into pathway activity,
mechanism, prognosis, or treatment claims. See
[`gbm-functional-proteotype.md`](gbm-functional-proteotype.md).

## Completed M06-03 typed glioma baseline lane

The additive M06-03 runtime now supports an explicitly annotated research path
for protein-abundance baselines. Scalar and interval state values are normalized
with a robust median/MAD scale, down-weighted with Huber influence, and fitted to
the signed RTK/PI3K/AKT/mTOR, p53/cell-cycle, IDH/HIF1A, mesenchymal, and
proliferation program graph using damped coordinate descent. Deterministic
request-digest perturbations provide bootstrap intervals, stability, driver
features, and feature/network ablation explanations; categorical, missing, and
unsupported values never become negative evidence.

The original M06-01 replay and scalar/interval/categorical baseline output remain
available for compatibility. Typed program states are research-use-only normalized
signals and do not establish measurement truth, diagnosis, prognosis, or treatment
response.

## Completed glioma immunopeptidomic presentation workbench lane

The caller-owned `glioma-immunopeptidomic-presentation/0.1.0` runtime is now
linked end to end in the scientific workbench. The UI validates exact HLA
identifiers, peptide evidence states, digest-bound caller PSSMs, and the
three-supported-peptide release gate before execution. Ranked allele-aware
presentation probabilities, seeded bootstrap intervals, binding/processing/
expression/variant ablations, model digests, limitations, and replay receipts
are rendered from backend results rather than synthesized in the browser. This
remains a licensed-model integration boundary: GLIO-PROTEOGEN ships no NetMHC
weights, does not claim cell-surface presentation or T-cell recognition, and
emits no neoantigen, clinical, or treatment recommendation.

## Completed GBM RNA composition workbench lane

The caller-owned `gbm-rna-composition/0.1.0` count-native runtime is now linked
end to end in the scientific workbench. Users can load or edit a bounded raw
count vector and positive lineage signatures, validate the exact simplex
contract, run the Dirichlet--multinomial adaptive-unknown solver, and inspect
lineage RNA weights, unexplained gene mass, KKT/objective-trace closure,
condition-number identifiability, and OOD diagnostics. Replay verification and
source-digest receipts are rendered from backend results. The lane never
relabels mixture weights as GBmap or histologic cell fractions and does not
bundle a fitted GBmap artifact or patient data.

## Completed M06-04 coupled glioma abundance lane

The additive M06-04 runtime now includes the locked
`locked_glioma_abundance_program_irls_v1` optimizer. It maps exact protein marker
identities into five GBM programs (RTK/PI3K/AKT/mTOR, p53/cell-cycle, IDH/HIF1A,
mesenchymal, and proliferation) and fits their signed relations with robust Huber
IRLS coordinate descent, feature-specific priors, assay precision, damping, and
hard domain bounds. A support gate requires four observed markers across two
programs; missing, unsupported, and non-numeric values are excluded rather than
interpreted as down-regulation. The output is a deterministic 90% research
interval with an objective/convergence diagnostic and exact replay. The prior
feature-wise optimizer and compatibility proxy remain unchanged.
Marker normalization preserves exact HGNC compound identities (including
`MKI-67` and `HIF-1A`) across the coupled program and feature-prior paths, while
rejecting substring-only matches.

## Completed M08-03 typed glioma program baseline lane

The additive M08-03 runtime now recognizes the
`glioma-protein-subtype-signed-program-graph/1.0.0` model family. Typed
observations carry standardized protein effects, standard errors, quality, and
explicit observed, left-censored, missing, or unsupported states. A robust
Huber coordinate-descent fit couples RTK/PI3K/AKT/mTOR, p53/cell-cycle,
IDH/HIF1A, mesenchymal, and proliferation programs through signed biological
relations, with ridge stabilization and a recorded objective trace.

The fit initializes each program from observed effects only and projects the
robust center onto any left-censor bound; censor-only programs start neutral on
the feasible side. The result reports bounded program intervals, thresholded activation labels,
evidence counts, stability, and a digest-seeded bootstrap. Missing programs
remain indeterminate rather than becoming negative evidence; insufficient
support abstains. The original statistical, pathway-weighted, and median
compatibility architectures remain unchanged. Typed output is a research
diagnostic, not a clinical subtype probability, prognosis, or treatment claim.

The typed solver now evaluates every signed-program sweep from one frozen
parent snapshot and applies Huber influence to both measurement and relation
residuals. A deterministic backtracking line search rejects objective-increasing
updates, and the accepted objective trace is digest-bound alongside the result.
This makes the fit invariant to relation declaration order and keeps robust
topology propagation auditable under strongly discordant protein evidence.

## Completed M08-02 typed glioma discordance representation lane

The additive M08-02 runtime fits paired transcript/protein effects with a
bounded translation prior, robust Huber coordinate descent, and explicit
one-sided censoring. Initial states are formed from observed assay effects only
and projected onto the tightest censor boundary; censor-only modalities remain
at the ridge-neutral feasible value. Censored residuals contribute only when a
candidate violates their upper bound, so detection limits cannot manufacture a
negative discordance. Deterministic bootstrap draws perturb both observed
effects and censor limits under the request-derived seed, with transcript-only,
protein-only, and translation-prior ablations retained in the receipt.

The historical hash-based representation path remains compatibility-only for
untyped requests. Typed output is research-use-only and does not emit a
diagnostic, prognostic, kinase, subtype, or treatment claim.

## Completed M08-04 typed glioma discordance lane

The additive M08-04 runtime now recognizes
`glioma-transcript-protein-discordance-program-irls/1.0.0`. Typed paired
transcript/protein effects are fitted across RTK/PI3K/AKT/mTOR, p53/cell-cycle,
IDH/HIF1A, mesenchymal, and proliferation programs with signed coupling,
quality/standard-error weighting, robust Huber coordinate descent, and a
digest-seeded bootstrap interval. Each iteration is a frozen-parent (Jacobi)
sweep over the signed program graph followed by a deterministic full-step
backtracking line search, so the objective trace is monotone and independent of
observation/program declaration order. Protein left-censoring contributes a
one-sided loss; missing and unsupported evidence is excluded rather than
treated as a negative observation.

The typed result exposes program-specific intervals, solver diagnostics,
deterministic replay, and explicit research-only limitations. The historical
single-posterior ABI remains unchanged and is not silently relabeled as a
glioma model; neither path emits subtype, kinase, diagnostic, prognostic, or
treatment claims. Initialization is censor-aware: paired observed discordance
centers are projected onto the tightest protein censor bound, while
censor-only programs start at the ridge-neutral feasible value.

## Completed M08-05 typed glioma mechanism-program lane

The additive M08-05 runtime now recognizes
`glioma-mechanism-program-irls/1.0.0`. It maps a locked glioma gene panel
(EGFR/ERBB2/ERBB3/FGFR3/MET/PDGFRA/PIK3CA/PIK3R1/AKT1/AKT2/MTOR,
TP53/MDM2/CDKN2A/CDKN1A/RB1/CDK4/CCND1, IDH1/IDH2/HIF1A/VHL/EGL9,
STAT3/CCL2/SOX2/TGFB1/TGFB2/VIM/ZEB1, and
OLIG2/MKI67/PCNA/TOP2A/CCNB1/CDK1/AURKA/MCM2/MCM6) into five signed
mechanism programs. Common `protein.`, `rna.`, `gene.`, and `transcript.`
assay namespaces and common HGNC compound spellings are normalized to these
gene keys. The same normalized identity map drives fitting, bootstrap, evidence,
and support accounting. Standard-error and
quality-weighted Huber coordinate descent fits observed and left-censored
evidence with ridge stabilization, edge-consistency penalties, damping, an
objective trace, and deterministic 64-replicate bootstrap intervals. Each
iteration is a frozen-parent sweep with a deterministic backtracking line
search, keeping the objective trace monotone and invariant to observation
order. Censored
program starts use observed effects only and project onto the tightest
detection bound; censor-only programs start neutral on the feasible side.
Bootstrap draws perturb the one-sided detection boundary itself, preserving
measurement uncertainty instead of only shifting an unused surrogate target.
Directly connected unobserved programs are propagated only through the signed
graph and retain zero measurement support.

The historical caller-declared/digest-only constraint path remains unchanged.
Typed estimates are normalized research signals with explicit program coverage
and are not biochemical activity, diagnosis, prognosis, or treatment evidence.

## Completed M08-06 typed glioma uncertainty lane

The additive M08-06 runtime now recognizes
`glioma-uncertainty-decomposition-bootstrap/1.0.0`. Typed observations retain
modality, glioma program, standard error, quality, and observed,
left-censored, missing, or unsupported state. A robust Huber location fit is
stratified by modality and program with an explicit ridge objective and
objective-safe backtracking. Digest-seeded bootstrap perturbations move the
declared censor boundary itself, then decompose measurement, sampling,
parameter, model-form, identification, support, and transport sensitivity into
all seven required dimensions.

The sensitivity envelope is explicitly internal bootstrap coverage rather than
external calibration. The original owner-review abstention path remains
unchanged for metadata-only requests, while typed output is a research
uncertainty diagnostic and cannot support diagnosis, prognosis, or treatment.

## Completed M09-04 typed glioma complex stoichiometry lane

The additive M09-04 runtime now recognizes the
`glioma-complex-stoichiometric-irls/1.0.0` model family. Typed requests carry
explicit member-level standardized effects, standard errors, quality weights,
essential/supporting roles, stoichiometric weights, and glioma program
identifiers. An alternating latent-effect/member-offset Huber IRLS fit keeps
member-specific departures visible while an essential-subunit bottleneck
prevents a strong supporting protein from masking a weak required member. Each
latent/offset sweep is accepted through a deterministic backtracking line
search, preserving a monotone objective trace across bottleneck and coherence
penalties.

The fit uses one-sided loss for left-censored members, excludes missing and
unsupported members, and requires at least two supported members, an essential
member, and a consistent program per complex. Latent starts are computed from
observed-member robust centers and projected onto the tightest censor bound;
censor-only complexes start at the neutral ridge point on the feasible side,
so a detection limit is never treated as a measured effect. Request-digest-seeded bootstrap
perturbations are stratified by essential versus supporting members so every
replicate retains the bottleneck stratum; they provide activity intervals,
stability, discordance, top member drivers, and explicit
essential-bottleneck/stoichiometric-coherence ablation effects. The original
artifact-reference estimator remains the compatibility path; typed activity is
a research signal and does not establish biochemical assembly, diagnosis,
prognosis, or treatment response.

## Completed M09-03 typed glioma complex baseline lane

The additive M09-03 runtime now recognizes the
`glioma-complex-baseline-huber/1.0.0` model family. Explicit standardized
protein effects are fitted across RTK/PI3K/AKT/mTOR, p53/DNA repair,
IDH/HIF1A, hypoxia/angiogenesis, and cell-cycle programs with quality and
standard-error weighting, robust Huber IRLS coordinate descent, ridge
stabilization, and signed program relations. The Jacobi update is followed by a
deterministic backtracking line search, so the recorded objective trace is
monotone under robust breakpoint crossings. Left-censored evidence uses a
one-sided detection-limit loss; missing and unsupported observations are
excluded and never become negative evidence. Program starts are computed from
observed effects only and projected onto the tightest left-censor bound;
censor-only programs start at neutral on the feasible side, preventing a
detection limit from acting as a measured negative effect.

The typed result carries a deterministic, program-stratified bootstrap
interval, evidence count, stability, residual discordance, top feature drivers,
signed-relation ablation effects, and a replay-bound objective trace digest. At
least three supported observations across two programs are required; otherwise
the lane abstains with review required. The original SHA-256-derived baseline
is retained as compatibility-only behavior, and the typed signal is not a
biochemical assay, diagnosis, prognosis, kinase estimate, or treatment claim.

The M09-02 and M09-03 solvers apply the censoring loss exactly: a left-censor
bound contributes no gradient anywhere in its feasible region and activates only
when the latent state exceeds that bound. This removes the small logistic-ramp
pull that could otherwise turn a satisfied detection limit into a weak negative
observation while preserving the existing request/result digests and replay ABI.

## Completed M07-05 typed glioma dosage constraint lane

The additive M07-05 runtime now recognizes the
`glioma-dosage-mechanism-irls/1.0.0` model family. Explicit copy-number or
proteotype effects are fitted across the five glioma programs with quality and
standard-error weighted robust IRLS, feature offsets, ridge stabilization, and
signed program relations. Left-censored dosage measurements use a one-sided
detection-limit loss; missing and unsupported states are excluded rather than
treated as suppression. Program starts use observed dosage effects only and
project onto the tightest censor bound, while censor-only programs start at
neutral on the feasible side.

The typed integration evaluates hard and soft constraints against fitted
feature states, preserves soft effects with ablation records, and emits
deterministic bootstrap intervals, stability, discordance, drivers, objective
traces, and replay diagnostics. The original hash-based constraint path remains
compatibility-only; typed dosage output is a research signal and not a
proteotype, biochemical, diagnostic, prognostic, kinase, or treatment claim.

## Completed M07-02 typed glioma copy-number representation lane

The additive M07-02 runtime now recognizes the
`glioma-copy-number-purity-irls/1.0.0` model family. Typed segment evidence is
converted from observed log2 ratios into purity-adjusted diploid-relative
effects, then fitted per feature with a damped Huber IRLS latent-value solver
and ridge stabilization. Left-censored segments contribute one-sided
detection-limit loss; missing and unsupported segments carry no numeric value
and force safe abstention when a requested feature lacks support.

The representation exposes model-derived channels (latent dosage, residual
scale, amplification/deletion fractions, allelic imbalance, mean purity, and
focal-segment score), deterministic bootstrap stability, discordance, genomic
drivers, and a replay-visible objective trace. Robust starts use observed
evidence only and project onto the tightest feasible censor boundary; bootstrap
replicates perturb both measured effects and detection limits under the same
request-derived seed. The original SHA-256 constructor
remains compatibility-only for untyped requests; typed output is a
research-use-only representation and does not emit a clinical copy-number call
or a parent proteotype claim.

## Completed M09-05 typed glioma mechanism-constraint lane

The additive M09-05 runtime now recognizes the
`glioma-mechanism-constraint-irls/1.0.0` model family. Typed member evidence is
scoped to five glioma mechanism programs and carries standardized effects,
standard errors, quality, stoichiometric weights, member roles, and explicit
observed/left-censored/missing/unsupported states. Each complex is fitted by a
damped Huber IRLS coordinate descent with one-sided censor loss, member-offset
ridge, stoichiometric coherence, essential-subunit bottleneck, and numeric
mechanism-constraint penalties. Censored member limits are used as one-sided
bounds (not `limit - 0.5*SE` surrogate observations), and latent starts are
robustly centered on observed members before projection to those bounds. Hard conflicts and unknown expressions abstain;
soft conflicts remain visible in the report.

Sixty-four deterministic, role-stratified bootstrap perturbations (bounded at
256) provide replay-stable intervals. Results expose convergence traces,
discordance, evidence counts, top member drivers, and bottleneck/coherence
ablations. Missing and unsupported observations are excluded rather than
treated as negative activity. The original digest-derived compatibility path
is untouched when typed observations are absent; typed output is research-use
only and does not establish biochemical activity, diagnosis, prognosis, or
treatment response.

## Completed M10-02 typed glioma representation lane

The additive M10-02 runtime fits protein effects from transcript, copy-number,
and phosphosite predictors with locked program-specific priors, robust Huber
coordinate descent, one-sided protein censoring, ridge stabilization, and
explicit modality ablations. Missing predictors are masked from the data term
instead of imputed as negative values. Bootstrap replicates now perturb observed
protein effects and censor limits separately, so detection-limit uncertainty is
visible in replay-stable intervals and stability summaries.

The historical transformation-only representation remains compatibility-only;
typed output is a research signal and does not emit a clinical, diagnostic,
prognostic, kinase, or treatment claim.

## Completed M10-03 typed glioma protein/RNA discordance lane

The additive M10-03 runtime now recognizes the
`glioma-protein-rna-discordance-programs/1.0.0` model family. Typed observations
carry paired standardized protein and RNA effects, modality-specific standard
errors, quality weights, and explicit observed, left-censored, missing, or
unsupported states. A coupled robust Huber IRLS fit estimates feature
discordance while shrinking each feature toward its glioma program coordinate
(RTK/PI3K/AKT/mTOR, p53/cell-cycle, IDH/HIF1A, mesenchymal, or proliferation).
Damping, ridge stabilization, and a recorded objective trace keep the fit
bounded and replay-auditable.

The program coordinates are coupled by the locked signed GBM relation graph
(RTK/PI3K/AKT/mTOR to p53/cell-cycle and proliferation, IDH/HIF1A to
mesenchymal, and mesenchymal to proliferation). Edge penalties are included in
the objective trace and evaluated from a Jacobi snapshot, so the result is
order-invariant while still allowing strong measured discordance to override a
soft biological prior.

Left-censored observations contribute only when the fitted discordance exceeds
the censoring boundary; missing and unsupported observations are excluded and
never converted into suppression. Request-digest-seeded NumPy bootstrap
perturbations provide interval bounds, stability, discordance magnitude, top
protein/RNA drivers, and program/protein-only/RNA-only ablation effects. The
typed lane abstains below two supported pairs or on non-finite/non-convergent
fits. The original sine-wave fixture and its scalar/interval/categorical shape
grammar remain the compatibility path, while typed output is research-use-only
and does not establish a molecular diagnosis, prognosis, mechanism, or
treatment response.

## Completed M10-04 typed glioma proteotype-factor lane

The additive M10-04 runtime now exposes the
`glioma-proteotype-factor-irls/1.0.0` model family through the locked
`locked_glioma_proteotype_factor_irls_v1` optimizer. A repository-owned GBM
marker panel maps EGFR/PI3K/AKT/mTOR, p53/cell-cycle, IDH/HIF1A, mesenchymal,
and proliferation proteins to latent programs. Robust Huber-IRLS coordinate
descent jointly fits those states with signed program edges and feature-specific
Normal priors, emitting deterministic 90% intervals and convergence diagnostics.
The program sweep uses a frozen parent vector followed by objective-safe
backtracking, so signed-edge coupling cannot make the replay trace increase or
depend on marker declaration order.
The lane requires four markers across two programs and abstains without that
topology support; it never falls back to independent posteriors. Existing
M10-04 metadata and measured-observation behavior remain compatibility paths,
and this research-only factor estimate is not a diagnosis, prognosis, or
treatment-response claim. HGNC compound symbols are normalized at the mapping
boundary, preserving namespace prefixes while resolving equivalent forms such
as `MKI-67`, `MKI_67`, and `MKI67` to the proliferation program.

## Completed M10-07 typed glioma discordance calibration lane

The additive M10-07 runtime now recognizes the
`glioma-discordance-selective-calibration/1.0.0` model family. Typed calibration
observations carry paired protein/RNA effects, propagated modality standard
errors, quality weights, a glioma program, explicit evidence state, subgroup,
and a discordant/concordant label. A quality-weighted damped robust logistic
IRLS fit learns the score-to-label relationship from those measurements rather
than deriving a query score from a digest. The fit records a bounded objective
trace and is replay-bound to the request digest. Its design matrix adds
ridge-regularized one-hot offsets for the five locked GBM programs, so sparse
program evidence shrinks toward the global calibration while program context
still changes the fitted score.

The fitted scores feed the existing leave-one-out conformal rank calibration,
OOD range check, and subgroup coverage disparity gate. Left-censored points are
penalized only while their fitted class remains on the unsupported side of the
censoring boundary; missing and unsupported points are excluded. Fewer than
eight supported labeled observations, a single observed class, non-finite
uncertainty, or a non-evaluable query abstains. The original digest-derived
score path remains compatibility-only, and typed output is an experimental
research calibration signal rather than a diagnosis, prognosis, mechanism, or
treatment recommendation.

## Completed M09-06 typed glioma complex uncertainty lane

The additive M09-06 runtime now recognizes the
`glioma-complex-activity-uncertainty-irls/1.0.0` model family. It accepts one
typed repeated-fit observation for each of the seven uncertainty dimensions,
with bounded instability scores, empirical coverage hits, quality weights, and
explicit supported-member counts. A quality-weighted Huber IRLS location is
fit for each dimension; support uncertainty adds an essential-member
bottleneck penalty so incomplete complex coverage cannot be hidden by an
aggregate score.

Each component receives a request-digest-seeded 64-replicate bootstrap interval,
stability, and repeat count. A pooled bootstrap coverage envelope gates support
at the locked 85--95 percent range. Observation order is canonicalized for
replay, missing dimensions and unsafe coverage abstain, and the historical
hash-derived decomposition remains unchanged when typed observations are not
provided. This lane is a research diagnostic for complex-member evidence, not
calibrated clinical confidence, biochemical activity, or treatment guidance.

## Completed M11-03 typed glioma feature lane

The additive M11-03 runtime now supports an opt-in
`glioma-signed-mechanistic-graph/1.0.0` model family. Scalar and interval
features are robustly median/MAD normalized and fitted with Huber-weighted,
signed activation/inhibition relation terms, ridge stabilization, and damped
coordinate descent. Deterministic request-digest perturbations provide a
bootstrap aggregate state interval; projected features retain their declared
lineage and the result adds derived signed-state and interval features.

Typed relations must carry an explicit finite weight. The legacy optional
relation field is not converted into a default edge strength; missing topology
strength causes the typed lane to abstain.

The declaration-only constructor remains compatible for all other model
families. The typed lane requires at least two numeric features and one
supported signed relation, abstaining when topology is insufficient or the
solver does not converge. Its outputs are research-use-only mechanistic
features, not variant interpretation, diagnosis, prognosis, kinase ownership,
or treatment recommendations.

## Completed M10-05 typed glioma constraint lane

The additive M10-05 runtime now accepts feature observations annotated to
RTK/PI3K/AKT/mTOR, p53/cell-cycle, IDH/HIF1A, mesenchymal, and proliferation
programs. Annotated observations are robustly median/MAD normalized and fitted
with Huber-weighted signed program coupling using frozen-parent damped Jacobi
coordinate descent and deterministic objective-safe backtracking;
normalization is estimated from observed values only; left-censored limits use
one-sided residuals, while missing and unsupported values are excluded. The
solver records a monotone objective trace alongside iterations/objective,
digest-seeded bootstrap intervals, top drivers, and signed-edge ablation effects
for every supported program.

Inhibitory (`direction=-1`) observations reverse the censor inequality in the
signed program coordinate. Starts are projected into the combined lower/upper
feasible interval, so a left-censored PTEN/NF1-like marker cannot be interpreted
as an exact repressive measurement.

The original closed true/false and numeric constraint evaluator, hard/soft
semantics, and replay envelope remain compatible. Strict `>`/`<` comparisons
now reject equality, and a left-censored limit must be strictly inside a `<`
bound before it can satisfy that constraint. If the typed graph has no
supported evidence or fails to converge, the service abstains with review
required rather than manufacturing a score. Program states are research-use
only signals and do not represent clinical mechanism, diagnosis, prognosis, or
treatment response.

## Completed M11-04 typed glioma mechanism lane

The additive M11-04 runtime now supports an opt-in
`glioma-mechanism-evidence-graph/1.0.0` family. Structured mechanism
observations carry standardized effects, standard errors, quality weights, and
explicit observed, left-censored, missing, or unsupported states. Signed
activation, inhibition, and coupling relations are fitted with robust Huber
loss, ridge stabilization, and frozen-parent damped Jacobi coordinate descent;
objective-safe backtracking preserves a monotone replay-auditable trace, and the
solver records objective and convergence diagnostics rather than returning a
fixed posterior.
Digest-seeded bootstrap perturbations produce per-mechanism posterior
intervals, while missing and unsupported observations are excluded from the
objective and cannot become negative evidence.

The original closed posterior/state method grammar remains compatible for all
other model families. The typed lane requires at least two supported mechanisms
and a signed relation, and abstains with review required when topology or
convergence is insufficient. Estimates are experimental standardized signals,
not clinical mechanism, diagnosis, prognosis, kinase ownership, or treatment
recommendations.

## Completed M12-03 typed glioma biomarker constraint lane

The additive M12-03 runtime now recognizes an opt-in
`glioma-biomarker-constraint-graph/1.0.0` model family. Numeric scalar and
interval features are fitted through signed activation, inhibition,
participation, precedence, and co-localization relations using robust Huber
loss, ridge stabilization, and damped coordinate descent. Deterministic
digest-seeded measurement perturbations produce a bootstrap state interval,
and projected features preserve their source lineage. Categorical features
and non-evaluable inputs remain non-evidence.

Every relation used by the typed fit must carry an explicit finite weight. The
legacy optional relation field is not converted into an invented default edge
strength; missing topology strength causes the typed lane to abstain.

The original invariant-only feature constructor remains compatible for other
model families. The typed lane requires two numeric features and a supported
signed relation, abstaining when topology or convergence is insufficient. Its
state is an experimental glioma research signal—not a clinical biomarker,
diagnosis, prognosis, or treatment recommendation.

## Completed M12-04 typed glioma panel mechanism lane

The additive M12-04 runtime now supports an opt-in
`glioma-panel-mechanism-evidence-graph/1.0.0` family. Panel mechanism
observations carry standardized effects, standard errors, quality weights, and
explicit observed, left-censored, missing, or unsupported states. Signed
activation, inhibition, and coupling relations are fitted with robust Huber
loss, ridge stabilization, and frozen-parent damped Jacobi coordinate descent;
objective-safe backtracking preserves a monotone replay-auditable trace.
Deterministic digest-seeded bootstrap perturbations produce posterior intervals
per panel mechanism. Initialization treats left-censored effects as upper bounds: observed
centers are clamped to feasible limits and censor-only mechanisms start at the
ridge-neutral feasible value.

The original closed posterior/state grammar remains compatible for other model
families. The typed path requires two supported mechanisms and a signed edge,
and abstains when topology or convergence is insufficient. Outputs remain
experimental standardized signals; left-censored effects are initialized as
feasible upper bounds rather than exact measurements. They are not clinical mechanism, diagnosis,
prognosis, kinase ownership, or treatment recommendations.

## Completed M12-05 typed glioma temporal program lane

The additive M12-05 runtime now recognizes typed temporal observations for the
five reviewable glioma programs (RTK/PI3K/AKT/mTOR, p53/cell-cycle, IDH/HIF1A,
mesenchymal, and proliferation). Each program is fitted over the ordered
history with quality/standard-error precision, robust Huber influence, ridge
stabilization, temporal smoothness, curvature control, and damped coordinate
descent. Missing and unsupported observations are excluded; left-censored
observations contribute a one-sided residual, so absence is never manufactured
as suppression.

The result includes quantized NumPy PCG64 request-digest bootstrap intervals,
thresholded activation labels, evidence counts, stability, cross-program
discordance, top drivers, solver objective-trace digest, and interval-supported
change points. The original opaque objective grammar remains compatibility-only
and unchanged for untyped requests. This is an experimental longitudinal
molecular signal, not validated tumor evolution, prognosis, diagnosis, or
treatment response.

## Completed M12-06 typed glioma perturbation response lane

The additive M12-06 runtime now supports an opt-in
`glioma-panel-perturbation-response-graph/1.0.0` family. Paired baseline and
perturbed assay replicates are fit with quality-weighted Huber IRLS arm
locations, conventional midpoint-MAD scaling for even replicate counts,
robust finite differences, and a bounded logistic response mapped to the
caller's response envelope. Digest-seeded bootstrap resampling yields
replayable intervals, robust standard errors, and explicit replicate counts.

The compatibility scalar path remains unchanged. Typed requests require at
least three finite replicates per arm for every supported scenario; missing
replicates abstain without a surface and never become negative evidence. This
is an experimental sensitivity projection, not a causal intervention,
diagnostic, prognostic, kinase-ownership, or treatment-response claim.

## Completed M11-06 typed perturbation sensitivity lane

The additive M11-06 research runtime now fits typed proteomic replicate evidence
instead of deriving a response from an upstream digest. Each perturbation carries
baseline and perturbed replicate vectors, a bounded quality weight, and the
declared perturbation kind. Arm locations use damped Huber IRLS with a midpoint
median absolute-deviation scale for even replicate counts;
the reported effect is a finite-difference change in robust arm location, mapped
through a bounded hyperbolic response envelope. This is a reproducible sensitivity
estimate, not a causal intervention or a clinical response model.

Uncertainty is generated by deterministic hash-seeded resampling of each arm and
nearest-rank 90% bootstrap bounds (64 draws by default, 256 maximum). The response
also reports the raw effect delta, robust standard error, replicate count, and
assumptions so a reviewer can distinguish measurement uncertainty from the locked
response transform. Fewer than three finite replicates per arm, non-positive
quality, unsupported markers, or a missing negative control produce a typed
abstention rather than a synthetic score. Opaque artifact references remain
immutable and are not traversed. The M11-06 route remains provisional: typed
replicate requests activate this glioma-specific research model, while legacy
opaque requests safely abstain instead of receiving a digest-derived score. The
lane is therefore a reviewable replacement surface, not a governed clinical API.

## Completed M13-03 typed mechanistic evidence lane

The additive M13-03 research runtime now consumes typed glioma observations for
proteins, phosphosites, pathways, and complexes. It solves a fixed signed
RTK/PI3K/AKT/mTOR, p53/cell-cycle, IDH/HIF1A, proliferation, and mesenchymal
graph with damped Huber IRLS coordinate descent, one-sided left-censoring loss,
ridge stabilization, convergence diagnostics, and deterministic digest-seeded
bootstrap intervals. Pathway activity is propagated through the graph rather
than computed as independent digest or weighted-average formulas; replicated
observations yield non-degenerate uncertainty and order-invariant receipts.
Initialization is censor-aware: left-censored effects are upper bounds with a
ridge-neutral feasible start, never exact locations.

Missing and unsupported observations are ignored as evidence, while insufficient
typed support and legacy opaque requests abstain instead of fabricating a score.
The response reports evidence coverage, signed regulatory balance, topology
support, and measurement/topology limitations. It does not estimate kinetics,
spatial state, kinase ownership, prognosis, treatment response, or causality, and
the research lane is not a governed clinical API.

## Completed M13-04 typed glioma proteotype mechanism lane

The additive M13-04 runtime now supports an opt-in
`glioma-proteotype-mechanism-evidence-graph/1.0.0` family. Typed proteotype
mechanism observations carry standardized effects, standard errors, quality
weights, and explicit observed, left-censored, missing, or unsupported states.
Signed activation, inhibition, and coupling relations are fitted with robust
Huber loss, ridge stabilization, frozen-parent damped Jacobi coordinate descent,
and objective-safe backtracking; deterministic digest-seeded bootstrap posterior
intervals remain replayable from the request digest.

The original caller-declared posterior/state grammar remains compatible for
other model families. The typed path requires two supported mechanisms and a
signed edge, abstains on insufficient topology or convergence, and preserves
counter-evidence. Outputs remain experimental proteotype signals—not clinical
mechanism, diagnosis, prognosis, kinase ownership, or treatment recommendations.

## Completed M13-05 typed glioma temporal lane

The additive M13-05 research runtime now fits typed longitudinal glioma program
effects instead of assigning caller-declared labels a fixed probability. Each
time point identifies one of five reviewable programs (RTK/PI3K/AKT/mTOR,
p53/cell-cycle, IDH/HIF1A, mesenchymal, or proliferation), a standardized signed
effect, standard error, quality weight, and observed/left-censored/missing/
unsupported evidence state. Missing and unsupported points are excluded from
the objective; left-censored points contribute only a one-sided residual.

The model uses damped Huber IRLS coordinate descent with first-order temporal
smoothing, curvature control, ridge stabilization, convergence checks, and a
request-digest-seeded 64-draw perturbation interval. Every state reports an
interval, evidence count, stability, discordance, top program drivers, and the
objective-trace digest; change points use the same signed bootstrap deltas.
Initialization is censor-aware: observed time-point centers are projected onto
the tightest left-censor limits, while censor-only points start at the
ridge-neutral feasible value before temporal interpolation and graph updates.
Legacy opaque objective requests remain a compatibility-only grammar and do not
receive a synthetic typed score. This is a research-use-only temporal signal,
not a diagnosis, prognosis, treatment recommendation, or kinase-ownership
claim.

## Completed M13-06 typed glioma perturbation lane

The additive M13-06 research runtime now has a typed perturbation path over the
same glioma program vocabulary. A scenario carries a signed baseline-to-
perturbed effect, standard error, quality weight, and observed/left-censored/
missing/unsupported state. Robust Huber coordinate descent fits direct program
effects while enforcing signed RTK/PI3K/AKT/mTOR, p53/cell-cycle,
IDH/HIF1A, mesenchymal, and proliferation edge coherence. Deterministic
request-digest perturbations produce effect intervals, stability, discordance,
top drivers, and an objective-trace digest for replay.

The historical bounded replay ABI remains compatibility-only. Missing and
unsupported typed scenarios are excluded and an all-missing request abstains;
the lane never turns an unsupported perturbation into a negative biological
finding. These program effects are research-use-only sensitivity signals, not
causal intervention estimates, kinase ownership, treatment recommendations, or
clinical evidence.

## Completed M14-05 typed glioma temporal lane

The additive M14-05 runtime now fits typed microenvironment temporal program
effects with standard-error and quality weighting, Huber robustness, temporal
smoothing, curvature control, and one-sided left-censoring. Initialization uses
quality-weighted observed centers while clamping to tightest censor limits;
censor-only cells start at the ridge-neutral feasible value instead of treating
an upper bound as an exact measurement. Deterministic perturbations produce
replayable intervals, and each trajectory state reports empirical bootstrap
support for its threshold class rather than a fixed confidence. The legacy
metadata-replay path remains compatible, and typed trajectories are
research-use-only signals.

## Completed M14-06 typed glioma perturbation lane

The additive M14-06 runtime now includes a typed perturbation model over the
same five glioma signaling programs. It fits signed scenario effects with
Huber-robust coordinate descent, ridge stabilization, and explicit program-edge
coherence rather than using the legacy absolute-difference proxy. Request-
digest-seeded bootstrap perturbations produce replayable intervals, stability,
discordance, top drivers, and numerical measurement/topology leave-one-family-
out ablation deltas from the same robust graph solver.

Initialization is censor-aware as well: observed scenario centers are projected
onto tightest left-censor limits, and censor-only programs begin at the
ridge-neutral feasible value. This prevents an upper bound from becoming a
synthetic observation before signed-edge propagation begins.

Missing and unsupported typed evidence is excluded and cannot become a negative
response; incomplete typed surfaces abstain with a human-review requirement.
The historical scalar sensitivity ABI remains available for compatibility only.
This lane is research-use-only and does not infer causality, kinase ownership,
treatment effects, prognosis, or clinical state.

## Completed M14-04 typed glioma network lane

The additive M14-04 runtime now consumes explicit protein/PTM mechanism
observations instead of relying on caller-declared posterior strings. A robust
Huber coordinate-descent solver fits signed RTK/PI3K/AKT/mTOR, p53/cell-cycle,
IDH/HIF1A, mesenchymal, and proliferation coupling, then maps latent states to
bounded posterior-like research scores. Deterministic request-digest bootstrap
draws provide intervals, stability, discordance, evidence counts, top drivers,
and numerical measurement/topology leave-one-family-out ablation effects;
missing and unsupported observations are excluded rather than treated as
negative evidence. Left-censored observations seed feasible upper-bound starts:
observed centers are clamped to their tightest limit and censor-only programs
start at the ridge-neutral feasible value.

The opaque posterior/state grammar remains compatibility-only and the typed lane
is review-gated. It does not claim causal mechanism, clinical probability,
prognosis, kinase ownership, or treatment effect.

## Completed M15-03 typed glioma feature lane

The additive M15-03 runtime now turns typed pathway/topology feature evidence
into derived complex-activity program features using robust Huber coordinate
descent over signed glioma network edges. It preserves the caller features and
adds request-digest-seeded bootstrap bounds, stability, discordance, evidence
counts, top drivers, and topology/measurement ablation explanations for each
program. Missing and unsupported typed features are excluded; an all-unsupported
request abstains with review required.

The original unit/topology/perturbation constructor remains unchanged for legacy
requests. Derived features are research-use-only and do not claim causality,
clinical state, prognosis, kinase ownership, or treatment effect.

## Completed M15-04 typed glioma mechanism graph lane

The additive M15-04 runtime now supports an opt-in
`glioma-complex-activity-mechanism-graph/1.0.0` family. Typed observations
represent signed RTK/PI3K/AKT/mTOR, p53/cell-cycle, IDH/HIF1A, mesenchymal, and
proliferation program effects with standard errors, quality weights, and
explicit observed, left-censored, missing, or unsupported states. A bounded
signed relation graph is fitted with Huber-robust coordinate descent, ridge
stabilization, convergence diagnostics, and deterministic digest-seeded
bootstrap intervals. Relation coherence propagates activity to connected
programs instead of returning a fixed posterior.

Each estimate retains direct evidence counts, stability, discordance, relation
drivers, and numerical measurement/topology ablation deltas. Those deltas are
leave-one-family-out refits from the same solver (measurement-only and
topology-only), not prose proxies. Missing and unsupported observations are
excluded and insufficient graph support abstains for human review. The legacy
posterior/state grammar remains unchanged for compatibility; typed mechanism
activity is research-use-only and is not a clinical probability, causal claim,
prognosis, kinase-ownership decision, or treatment recommendation.

## Completed M15-05 typed glioma temporal graph lane

The additive M15-05 runtime now supports the
`glioma-complex-activity-longitudinal-graph/1.0.0` model family. Longitudinal
observations carry signed standardized effects for the five glioma programs,
assay errors, quality weights, and explicit observed, left-censored, missing,
or unsupported states. A damped Huber coordinate-descent fit combines temporal
smoothing with directional RTK/PI3K/AKT/mTOR, p53/cell-cycle, IDH/HIF1A,
mesenchymal, and proliferation coherence without using future observations to
label an earlier time point. Initialization is censor-aware: observed centers
are clamped to tightest left-censor limits, and censor-only cells start at the
ridge-neutral feasible value rather than treating an upper bound as an exact
measurement.

Digest-seeded bootstrap perturbations provide replayable intervals and
posterior support for thresholded trajectory labels. Cross-band transitions
produce detected change-point objects; missing or unsupported points remain
explicitly indeterminate and insufficient typed histories abstain for human
review. The historical metadata-replay path remains compatible and retains its
provisional, non-biological semantics. Typed trajectories are research-use-only
signals, not diagnosis, prognosis, causal intervention, kinase ownership, or
treatment recommendations.

## Completed M15-06 typed glioma perturbation sensitivity lane

The additive M15-06 runtime now fits typed longitudinal perturbation effects over
the glioma program graph rather than returning a fixed absolute-difference proxy.
Observed and left-censored effects are weighted by standard error and quality,
robustified with Huber loss, stabilized with ridge regularization, and coupled by
signed RTK/PI3K/AKT/mTOR, p53/cell-cycle, IDH/HIF1A, mesenchymal, and proliferation
edges using deterministic damped coordinate descent. Solver convergence and the
objective trace are included in the surface metadata for replay auditability.

Request-digest-seeded bootstrap perturbations produce bounded intervals, stability,
discordance, top program drivers, and numerical measurement/topology
leave-one-family-out ablation deltas. Removing typed observations exposes the
topology-only propagation; removing signed edges exposes measurement-only
support.
Typed starts preserve the same evidence semantics: observed deltas seed a
quality-weighted location projected onto the tightest left-censor bound, while
censor-only programs start at the ridge-neutral feasible value. A detection
limit therefore cannot become a synthetic longitudinal effect before graph
propagation.
Missing and unsupported scenarios are explicitly excluded; incomplete typed
surfaces abstain with human review rather than manufacturing a negative response.
The historical scalar sensitivity ABI remains available for compatibility only.
This lane is research-use-only and does not claim causality, prognosis, kinase
ownership, treatment effect, or clinical state.

## Negative cross-assay feasibility result

An exact development-only join found all 88 PDC000515 pairs in PDC000514, but
the assay-specific reference UUID sets had zero overlap and therefore cannot be
pooled or interpreted as occupancy. In leakage-safe 5x3 patient-grouped nested
cross-validation, the protein model recovered 71/88 held-pair directions, the
phosphosite model 66/88, and nested late fusion 67/88. Fusion-only and
protein-only correct calls were 2 and 6 respectively (exact McNemar `p=.289`).
The fusion candidate therefore supplied no held-pair evidence beyond protein
alone and remains `not_fitted`. This is a negative feasibility audit, not release
validation, and it removes late fusion from the active replacement queue.

## Completed Reactome conditional-transition model

`kncc-reactome-conditional-transition/1.0.0` is now a fitted, mounted API/CLI
research lane rather than a source-admission placeholder. Its compact source
catalog locks the exact PDC000514 protein feature axis, a pre-outcome ten-event
Reactome V97 glioma-domain panel, nearby nonselections, parent/source hashes,
deterministic patient/gene/pathway order, and exact membership indices. The
fitted artifact adds a 1,872-gene global-plus-conditional design and 256
patient-bootstrap source fits without bundling patient values, identifiers,
identifier-derived hashes, scores, residuals, fold membership, or bootstrap
resample indices.

All source statistics and loadings are refit inside eight held-patient folds;
five held-gene folds within each patient produce 520 reconstruction evaluations.
The joint dictionary's median standardized MAE is 0.5554163035 versus
0.5622984198 for the global-only model, a modest median relative improvement of
1.20459348%. All ten individual cohort leave-pathway-out q05--q95 intervals
cross zero, so runtime pathway coordinates require strict request-specific
support and remain conditional concordance—not activation, flux, causality, or
clinical evidence. This was the tenth real inference lane when completed. See
[`kncc-reactome-conditional-transition-source.md`](kncc-reactome-conditional-transition-source.md)
and
[`kncc-reactome-conditional-transition-model.md`](kncc-reactome-conditional-transition-model.md).

## Completed Reactome participant-set transition model

`kncc-reactome-complex-transition/1.0.0` adds a separate fitted view of the
same PDC000514 protein cohort. Its source catalog locks a prespecified
repository-authored pilot panel of 28 exact Reactome V97 participant sets across
11 explicitly pilot domains, informed by public glioma biology and the source
paper. Selection does not read abundance arrays during import, but the panel is
not demonstrated outcome-independent. The catalog also locks exact
UniProt/HGNC/PDC feature projections, direct pathway bindings, nesting,
same-family overlap, inverse membership degree, and leave-family-out metadata.
The fitted artifact contains 28 separate missing-aware rank-one Huber models,
146 member slots over 120 unique proteins, and 128 patient-bootstrap loading
fits without bundling patient values, identifiers, fold assignments,
coordinates, predictions, residuals, or resample indices.

Eight patient-grouped outer folds produce 14,988 held-member reconstructions.
Mean standardized MAE is 0.6989814224 versus 0.8769685109 for the training-center
baseline and 0.9407301748 for zero transition; direction accuracy is
0.7255137443. The patient-cluster median relative gain is 0.1489483703, with a
nominal 90% interval of [0.0990936656, 0.1805654575]. All preprocessing,
factor, and evaluable coordinate fits converge, while 56 held coordinates
abstain for insufficient remaining member support. This is internal
source-cohort reconstruction, not external validation.

Runtime preserves exact and one-sided-censored transition evidence, solves a
real Huber-ridge coordinate against each fitted loading, separates measurement
and fitted-source bootstrap sensitivity, and reports source-processing,
signed-uniform-loading, top-member, and same-family-overlap ablations. Its
strict ceiling is participant-set protein-transition concordance—not complex
assembly, biochemical activity, essentiality, stoichiometry, causal mechanism,
clinical state, or treatment response. This lane raises the current independent
inference inventory from ten to eleven. See
[`longitudinal-gbm-complex-transition.md`](longitudinal-gbm-complex-transition.md).

## Completed KNCC/Neftel conditional-transition model

`kncc-neftel-program-transition/1.0.0` adds a second fitted view of the exact
PDC000514 protein cohort, bound to the exact Neftel Table S2 MES2, MES1, AC,
OPC, NPC1, NPC2, G1/S, and G2/M marker identities. The source projection maps
289 union markers before eligibility and fits a fixed 256-feature union across
104 strict matched primary/recurrent patient groups. The artifact contains one
global loading, eight conditional program loadings, eight patient-grouped outer
folds with five held-marker folds, and 128 patient-bootstrap refits without
shipping patient values, identifiers, identifier-derived hashes, scores,
residuals, fold assignments, or bootstrap indices.

The joint dictionary's median standardized held-out MAE is 0.5754778047 versus
0.6039095267 for global-only and 0.5177467313 for equal marker membership. Its
patient-cluster median relative gain over global-only is 0.0248465156 with a
nominal 90% interval of [0.0153265550, 0.0380342956], while its gain relative to
equal membership is -0.0987176386 with [-0.1155036986, -0.0777444485]. All
eight leave-program-out intervals cross zero. That negative comparator result
is retained as a release gate: the runtime computes the fitted coordinates but
caps every estimate `LIMITED`, and abstains when exact evidence or reliability
support is inadequate. This is the twelfth real inference lane. See
[`longitudinal-gbm-neftel-transition.md`](longitudinal-gbm-neftel-transition.md).

## CPTAC GBM cis-dosage local-only implementation

A read-only, exact-hash audit of the CPTAC GBM Table S2 workbook established a
scientifically defensible **local-build** path for gene-level cis-dosage
evidence, but not authority to bundle a fitted coefficient artifact. That path
is now implemented as the local-only `cptac-gbm-cis-dosage` CLI with
`fit-local`, `profile`, `analyze`, `verify`, and `verify-source` commands, plus a
stateless library query over caller-built artifacts. It has no public
HTTP route and is not an additional mounted inference lane. Exact
one-to-one HGNC mapping produced 10,430 genes across CNV, RNA, and protein for 96
patient groups; 9,457 genes passed complete five-fold patient-grouped
out-of-fold support. Across supported genes, median held-out RNA-from-CNV R²
was 0.0668 and protein-from-CNV+RNA R² was 0.2188. Protein prediction improved
over CNV-only by median R² 0.1776 but did not improve over RNA-only genome-wide
(median delta R² -0.0060); 334 genes passed the stricter joint/sensitivity
screen. Table S3 flags were used only as post-hoc same-cohort concordance and
their zeros were not treated as negatives.

This is a completed local implementation, not an additional shipped HTTP
inference lane. Until supplement redistribution/derived-artifact terms are admitted, the
implemented product remains a same-user exact-source local builder plus a local,
stateless gene-level evidence query. It never persists sample headers, fold membership,
patient-level predictions, or identifier-derived hashes, and its observational
standardized decomposition cannot be called causal mediation. See
[`cptac-gbm-iprofun-foundation.md`](cptac-gbm-iprofun-foundation.md).

An exact iProFun R-oracle reproduction and permission to redistribute a fitted
public artifact remain future source-admission work; neither is implied by the
local implementation.

## CPTAC GBM transcript–protein conditional-association local implementation

`cptac-gbm-transcript-protein-discordance/1.0.0` now provides a second
exact-source local-build path over the 96 resolved patient groups and 10,430
CNV/RNA/protein genes in CPTAC GBM Table S2. For one through 256 predeclared
genes, it compares five-fold, fold-local Huber-IRLS
`Protein ~ RNA + CNV` predictions with RNA-only, CNV-only, and training-median
comparators. It reports common-support held-out R², Spearman correlation, MAE,
residual MAD, both incremental-R² ablations, and raw-scale conditional RNA
coefficient stability. Each accepted gene also receives 128 deterministic,
fold-stratified patient-bootstrap full refits and nominal 90% nearest-rank
intervals.

This is an implemented fitter, aggregate artifact, local query, and exact replay
contract—not a bundled fitted cohort artifact. The repository therefore makes
no source-derived gene-performance or biological-validation claim for this lane.
The local runtime accepts artifact and gene identifiers only; patient
measurements, OOF arrays, patient identifiers or hashes, fold membership, and
residual vectors cannot cross the artifact/query boundary. No HTTP route is
mounted, and supplement redistribution remains `local_only_terms_unverified`.

Every estimable gene is capped `LIMITED`. Positive and inverse labels mean only
that nominal source-cohort intervals support a conditional RNA coefficient and
incremental prediction over CNV-only. They are not biological buffering,
causal mediation, a patient prediction, or an iProFun result. The repository's
zero-boundary rule has no genome-wide multiplicity calibration or independent
validation. The governed M08 v1 routes, schemas, digests, and provisional
M08-03/M08-04/M08-05 engines remain unchanged and remain in the stand-in debt
inventory. See
[`cptac-gbm-transcript-protein-discordance.md`](cptac-gbm-transcript-protein-discordance.md).

## Prioritized replacement queue

1. **GBM microenvironment inference.** The mounted
   `gbm-microenvironment-graph/1.0.0` bridge now reports source-locked
   Neftel bulk-program concordance through a signed ECGI graph while preserving
   missingness. Replace the remaining cell-fraction gap with an explicitly
   licensed GBM single-cell reference and count-native Bayesian mixture method;
   the protein-only bridge must continue to abstain from cell-fraction claims.
2. **Broader GBM complex/pathway evidence graph.** The source-locked PDC000514
   participant-set transition lane now supplies a real protein-only complex
   component, but it does not complete a multimodal pathway graph. Replace the
   remaining synthetic demo topology with a versioned Reactome graph and a
   source-admitted matched PDC000204/PDC000205 protein/phosphosite cohort. A
   read-only byte audit found the same 110 unique non-pool aliquot labels in the
   same order across both assay maps and matrices, but this is not yet a patient
   join: the local bundle has no PDC000205 study/version record, no file-level PDC
   provenance, and no official case/specimen map. The separate PDC000204
   metadata reports 111 cases/aliquots, which is unresolved against the 110
   captured labels. The next lane is therefore design-only and admission-blocked;
   it must learn edge-family reliability inside nested case-group folds while
   retaining the real robust ECGI solver, explicit topology/modality ablations,
   and an internal-concordance-only ceiling. Exact byte locks, grouping,
   endpoints, leakage controls, gates, and blockers are specified in
   [`cptac-gbm-matched-evidence-graph-design.md`](cptac-gbm-matched-evidence-graph-design.md).
3. **Glioma immunopeptidomic presentation.** Bind exact HLA alleles and pinned
   pretrained processing/binding/presentation models, with allele support,
   calibration, and abstention exposed in every result. The first numerical
   step is now implemented as the caller-owned
   `glioma-immunopeptidomic-presentation/0.1.0` runtime: it executes supplied
   position matrices and processing coefficients, preserves missing/censored
   expression, computes deterministic bootstrap intervals and component
   ablations, and seals replay digests. No pretrained artifact is bundled, so
   this lane remains caller-owned and cannot make a source-derived GBM
   presentation claim until an explicitly licensed, calibrated model package is
   admitted. See
   [`glioma-immunopeptidomic-presentation.md`](glioma-immunopeptidomic-presentation.md).

The lower-risk M11 integration is complete: its research/v2 facade delegates to
the exact published GBM proteomic-axis ensembles without changing the frozen
governed M11 route. It remains a compatibility surface, not another model or a
scientific substitute for the replacement work above.

Each replacement must provide `profile`, synthetic `demo`, `analyze`, and exact
`verify` operations; immutable source and profile digests; strict typed missing and
censored states; uncertainty and ablations; source-derived or independently
calculated oracles; and non-prescriptive claim ceilings.

## Source-admission rule

A public URL is not a redistribution license. Raw workbooks, trained objects, or
third-party annotations are vendored only when their reuse terms are explicit and
compatible. Otherwise the repository may provide a hash-verifying user-side
importer, or the model remains permission-gated. Patient-level matrices are never
bundled merely because they appeared in supplementary material.
