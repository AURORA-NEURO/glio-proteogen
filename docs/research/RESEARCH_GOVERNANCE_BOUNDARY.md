# Research/governed boundary

The executable scientific work lives under `glio_proteogen.research`. It is an
additive research namespace: callers own their inputs, computations emit
content-addressed evidence, and every evaluator is research-use-only.

The frozen M03, M04, and M05 contracts remain separate. Their claim ceilings
intentionally exclude spectrum search, abundance estimation, peptide-to-protein
inference, proteoform/isoform inference, glioma biology, mechanism discovery,
and clinical or treatment claims. Governed source files retain an executable
import firewall against the research namespace.

The central FastAPI composition may mount seventeen narrow research adapter
modules exposing eighteen versioned routers. Twelve expose distinct
scientific-inference lanes as software surfaces (not a claim that their evidence
sources are statistically independent), one exposes an integrated KNCC
factor-graph composition of two existing exact child engines, and five are
compatibility facades. Typer exposes the thirteen HTTP computational surfaces
plus two separate local-only exact-source tools: `cptac-gbm-cis-dosage` and
`cptac-gbm-transcript-protein-discordance`. Neither CPTAC tool has a central
HTTP route, and neither increases the mounted surface or operation count. The
second tool reports only cohort-level conditional RNA--protein association
after including CNV; it is not biological buffering, an iProFun reproduction,
or a patient scorer, and governed M08 remains unchanged.
`/v1/research/proteogenomic-state`
accepts structured graph evidence for ECGI.
`/v1/research/gbm-proteomic-axes` accepts positive LFQ
measurements for an exact port of seven published GBM proteomic models.
`/v1/research/neftel-protein-programs` accepts standardized bulk-protein
contrasts and preserves the exact marker identities and ranks from Neftel Table
S2 while applying a separately identified repository-native evidence model.
`/v1/research/gbm-master-kinases` accepts standardized phosphosite contrasts and
computes independently authored concordance against 24 source-locked
subtype-specific SPHINKS/MK signatures.
`/v1/research/gbm-functional-proteotype` accepts standardized bulk-protein
contrasts and jointly estimates relative GPM, MTC, NEU, and PPR concordance
against exact Table 2d signatures. Table 2e pathways remain source-cohort
context only and never become sample pathway, subtype, or clinical inference.
`/v1/research/longitudinal-gbm` accepts ordered protein observations and
computes source-cohort concordance against a de-identified model fitted from
104 strict PDC000514 primary/recurrent pairs.
`/v1/research/longitudinal-gbm-phospho` independently accepts exact
ENSP-versioned PDC000515 phosphosite groups and projects raw T2-minus-T1
concordance through its source-locked sparse model. It never silently adjusts
for cognate protein abundance or fuses assays; both views are explicitly
`not_fitted`. `/v1/research/longitudinal-gbm-kinase-transition` compares
PDC000515 longitudinal phosphosite transitions with source-locked SPHINKS
signature directions. Because the source fit and runtime transition use the
same phosphosite assay family, this lane emits signature-transition
concordance only: it is neither biochemical nor causal kinase activity and is not
independent evidence.
`/v1/research/longitudinal-gbm-neftel-transition` fits one global
primary-to-recurrent concordance coordinate and eight coordinates conditional
on that global axis from 104 strict PDC000514 paired-patient bulk-protein
transitions. The conditional coordinates use the exact 256 training-eligible
protein markers admitted from Neftel Table S2, with overlap correction,
patient-grouped and held-marker validation, robust fitting, and patient-bootstrap
coefficient uncertainty. They are source-cohort bulk-protein marker-set
coordinates. Because the fitted dictionary did not outperform equal marker
membership and has no external validation, every estimable coordinate is
hard-capped `LIMITED`. They are not single-cell state abundance, cell fraction, subtype, patient
evolution, recurrence prediction, prognosis, or treatment evidence.
`/v1/research/longitudinal-gbm-reactome-transition` projects ordered KNCC-scale
protein observations onto one global recurrence-concordance coordinate and ten
fixed, Reactome V97 membership coordinates conditional on that global axis.
The repository-authored panel is pinned before runtime outcomes; it is not a
Reactome-provided GBM panel. Outputs are conditional source-cohort concordance,
not pathway activation, flux, causal tumor evolution, prognosis, or treatment
evidence.
`/v1/research/longitudinal-gbm-complex-transition` projects ordered KNCC-scale
protein observations separately onto 28 robust rank-one member-transition
coordinates over exact Reactome V97 participant sets in 11 repository-authored
pilot domains. The prespecified panel was informed by public glioma biology and
the PDC000514 source paper and selected without reading abundance arrays during
import; it is not demonstrated outcome-independent. The lane reports
source-cohort participant-set concordance, not physical
assembly, activity, essentiality, stoichiometry, causality, clinical state, or
treatment evidence.
`/v1/research/gbm-factor-graph` runs the exact PDC000514 Reactome and
PDC000515 SPHINKS signature-transition engines as two numerically independent
child blocks in deterministic serial order and nests their exact results and
receipts. Its 41-node topology has 39 annotation-only containment edges, zero
cross-block numerical edges, and no cross-modal fusion or feedback. It is an
integrated presentation/composition surface, not a new independent fitted model
or an additional validation source.
`/v1/research/gbm-rna-purity` accepts raw bulk RNA counts under an exact
primary-IDH-wildtype-GBM attestation and runs the published GBMPurity MLP through
an artifact-locked NumPy port. It emits one malignant-cell-fraction estimate,
not protein evidence, lineage composition, diagnosis, or clinical truth.

Five API-only compatibility facades reuse existing fitted lanes without
introducing another model or another evidence source.
`/v2/research/modules/m09/complex-transition-concordance` delegates exactly to
the fitted Reactome participant-transition lane. It may replace only synthetic
or digest-derived participant-set transition-concordance stand-ins; it does not
infer physical assembly, stoichiometry, essentiality, complex activity,
causality, prognosis, or treatment response.
`/v2/research/modules/m10/functional-proteotype` delegates exactly to the
source-locked Migliozzi four-axis bulk-protein estimator. It replaces only
synthetic or caller-declared M10 numerical stand-ins as research evidence and
does not emit pathway activity, mechanism, prognosis, perturbation response,
clinical class, or treatment guidance.

`/v2/research/modules/m11/protein-native-subtype` delegates exactly to the GBM
bulk-protein axis service, and
`/v2/research/modules/m14/microenvironment-protein-programs` delegates exactly
to the Neftel bulk-protein program service.
`/v2/research/modules/m15/longitudinal-recurrence-proteotype` delegates exactly
to the fitted KNCC/PDC000514 longitudinal protein service. They make fitted
evidence available at explicit M09, M10, M11, M14, and M15 research integration
boundaries; they do not supersede the governed module families or promote the
delegated outputs into subtype, cell-fraction, recurrence-prediction, clonal,
spatial, causal, or clinical claims.

Each mounted router exposes profile, synthetic demo, analysis, and replay
verification. The twelve independent scientific-inference lanes plus the one
composition surface account for fifty-two operations, while the five
compatibility facades account for twenty, for seventeen adapter modules,
eighteen routers, and seventy-two research operations in total. The adapters do not accept raw
mzML/FASTA bytes,
persist requests or results, call governed modules, or promote research output
into governed claims. Architecture
tests inventory the exact seventy-two operations and reject any additional
research surface.

The adapter import bridge is equally narrow. Every Python file under
`glio_proteogen.adapters` is scanned. `api.py` may import the sixteen approved
HTTP adapter modules that mount eighteen routers, while `cli.py` may import the
thirteen HTTP computational-surface adapters plus the two local-only CPTAC
adapters; the M09, M10, M11, M14, and M15
compatibility facades are deliberately API-only. Only each
narrow adapter may import its corresponding research implementation package,
and adapters that execute bounded work may reuse the research cancellation
primitive.
Relative-import spellings are resolved before this rule is checked, so other
adapters and deployment helpers cannot bypass the boundary.

The GBMPurity lane is the only mounted research surface that emits a cell
fraction. Its scope is raw bulk RNA for primary IDH-wildtype GBM and its single
output is malignant-cell fraction. The exact source tree, MIT model artifact,
5,829-gene order, source preprocessing, float32 weights, gene-coverage gate,
output clipping, and active-ReLU decomposition are content-bound. Because the
source release contains no calibrated ensemble, uncertainty is declared
unavailable. This lane does not authorize the protein-facing M14 facade to emit
fractions and does not promote any governed M14 placeholder.

The GBM model scores remain continuous bulk-proteome research evidence. Their
published zero-fill convention is disclosed with coverage and abstention, and
their tree-path explanations are not represented as causal importance. They do
not establish a cell fraction, diagnosis, clinical subtype, prognosis, or
treatment response. The learned weights, source commit, converted artifact,
runtime semantics, and author-supplied software oracle are documented in
`gbm-proteomic-axes.md`.

The Neftel program outputs are bulk-protein program evidence, not a reproduction
of the paper's single-cell scoring pipeline. They do not estimate cell-state
fractions, malignant-cell identity, plasticity, diagnosis, or subtype. The exact
source workbook digest, marker/rank digest, HGNC normalization, robust estimator,
rank-enrichment statistic, permutation/FDR procedure, support gates, ablations,
and limitations are documented in `neftel-protein-programs.md`.

The M09 facade is compatibility metadata and transport around the exact
Reactome participant-transition request, result, profile, and replay semantics.
It can displace only participant-set transition-concordance stand-ins and adds
no physical assembly, stoichiometry, essentiality, activity, causality,
prognosis, or treatment claim. The M10 facade is compatibility metadata and transport around the exact
Migliozzi functional-proteotype request, result, profile, and replay semantics.
It can displace only synthetic or caller-declared M10-03/M10-07 numerical
stand-ins as research evidence and supersedes no M10 responsibility. The M11
facade is compatibility metadata and transport around the exact GBM
protein-axis request, result, profile, and replay semantics. It adds no subtype
posterior or independent evidence and supersedes no M11 responsibility. The M14
facade similarly delegates exact Neftel bulk-protein program evidence. It adds
no deconvolution, cell abundance, immune composition, spatial localization, or
independent evidence and supersedes no M14 responsibility. The M15 facade
delegates exact KNCC longitudinal protein evidence and adds no recurrence
prediction, clonal evolution, causal mechanism, or external validation. Their
responsibility mappings and claim ceilings are documented in
`m09-complex-transition-facade.md`,
`m10-functional-proteotype-facade.md`,
`m11-protein-native-subtype-facade.md`, and
`m14-microenvironment-protein-programs-facade.md`, and
`m15-longitudinal-recurrence-facade.md`.

The master-kinase outputs are independent signature concordance, not a port or
retraining of SPHINKS/MK. They do not claim calibrated kinase activity,
causality, subtype probability, diagnosis, or therapeutic response. The exact
CC-BY workbook, source-table projections, duplicate-row collapse, one-sided
robust estimator, competitive null, fixed 24-hypothesis FDR family,
uncertainty, support gates, and limitations are documented in
`gbm-master-kinase-concordance.md`.

The functional-proteotype output is a joint, relative bulk-protein concordance
with four source-locked Table 2d signatures. It does not choose a subtype or
convert source Table 2e pathways into sample-level activity. The admitted
aggregate source data, constrained robust objective, competitive rank family,
bootstrap, support gates, ablations, and claim ceiling are documented in
`gbm-functional-proteotype.md`.

The longitudinal output is protein-level source-cohort concordance, not a tumor
evolution, recurrence, prognosis, or treatment-response determination. Patient
matrices and row-level identifiers are not packaged. The versioned PDC source
lock, strict-pair construction, nested cross-validation, privacy enumeration,
bound-aware robust estimator, coupled uncertainty, ablations, exact PELT
oracle, and limitations are documented in
`longitudinal-gbm-protein-concordance.md`.

The longitudinal phosphosite output is raw phosphosite source-cohort
concordance, not occupancy, kinase activity, protein/phosphosite fusion,
recurrence prediction, prognosis, or treatment evidence. Its exact PDC000515
source snapshots, support-suppressed feature inventory, patient-grouped nested
evaluation, exact full-refit sparse bootstrap ensemble, quality gates, and
privacy checks are documented in
`longitudinal-gbm-phosphosite-foundation.md`.

The longitudinal kinase-transition output is a PDC000515-to-SPHINKS
signature-transition concordance check. It preserves the source-selected
kinase/signature family and reports source-fit stability, runtime support,
uncertainty, and abstention, but it does not estimate biochemical kinase
activity, infer a causal regulatory event, or contribute evidence independent
of the phosphosite assay used to fit it. Its exact source locks, fixed
hypothesis family, grouped bootstrap ensemble, same-assay limitation, and
privacy boundary are documented in `longitudinal-gbm-kinase-transition.md`.

The longitudinal Reactome output uses an exact ten-pathway, repository-authored
glioma-domain panel over source-locked Reactome V97 memberships. It reports a
global-adjusted membership coordinate with support, uncertainty, overlap,
request-reconstruction, and ablation evidence. It is not pathway activation or
flux, and PI3K/AKT is always marked overlap-confounded. TGF-beta EMT is excluded
because GBM is not epithelial; Apoptosis is not added to optimize observed
performance. The locked source binding is documented in
`kncc-reactome-conditional-transition-source.md`; the fitted recipe,
same-cohort evaluation ceiling, runtime solver, uncertainty decomposition, and
support gates are documented in
`kncc-reactome-conditional-transition-model.md`.

The longitudinal Reactome participant-set output is a separate fitted lane over
28 exact V97 entities in 11 repository-authored pilot domains. The prespecified
panel was informed by public glioma biology and the PDC000514 source paper and
selected without reading abundance arrays during import; it is not demonstrated
outcome-independent. The lane learns one
missing-aware robust rank-one member-transition pattern per participant set,
then applies a bound-aware Huber-ridge coordinate to caller evidence. The
patient-grouped held-member evaluation, 128 fitted-source bootstrap draws,
measurement/source uncertainty decomposition, and source-processing, loading,
member, and overlap ablations remain internal PDC000514 concordance evidence.
They do not establish assembly, biochemical activity, an essential-subunit
constraint, stoichiometry, occupancy, causality, clinical prediction, or
treatment utility. Exact sources, panel membership, fit, evaluation, runtime
semantics, and claim ceiling are documented in
`longitudinal-gbm-complex-transition.md`.

The KNCC factor-graph composition preserves its conditional-Reactome and
kinase-transition child claim ceilings without reinterpretation. The protein
block is Reactome source-cohort concordance, not activation or flux. The
phosphosite block is SPHINKS
signature-transition concordance, not kinase activity or causality. Both remain
same-source-cohort evidence rather than external validation. Exact child
request, profile, and result digests are nested under an outer topology,
source-inventory, profile, request, and result receipt; replay recomputes and
checks both children independently. The topology, bindings, interfaces, limits,
and claim ceiling are documented in `kncc-gbm-factor-graph.md`.

Experimental kinase inference belongs only to the research namespace. ECGI's
kinase output is a local phosphosite-substrate estimate with explicit support
and abstention; an optional external KINOPHOS profile is compared but never
merged or allowed to override it. The master-kinase lane separately compares
observations with frozen GBM subtype signatures and neither consumes nor
overrides ECGI or KINOPHOS estimates. The longitudinal kinase-transition lane
is a third, explicitly non-independent same-assay signature-concordance view;
it does not consume or override the other kinase outputs. The factor-graph
surface only presents that exact child result beside the independent Reactome
child; it introduces no feedback path. Governed M16 ownership, routes, schemas,
and digests are unchanged.

This is a safety boundary, not a claim that the research implementation is
clinically validated. Promotion into a governed module requires an owner-frozen
ABI, licensed raw/reference catalogue, search and quantification policy,
external validation cohorts, privacy/consent review, and an explicit replay and
safe-abstention contract. Until those artifacts exist, the research verifier
checks only locked computation identity, solver trace, result semantics,
fixture/scenario inventory, package reachability, and declared evidence—not
biological truth, clinical validity, or treatment utility.
