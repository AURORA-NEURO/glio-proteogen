# Glioma frontier research roadmap

The objective is a reproducible glioma proteogenomics platform whose useful
scope grows through measured independent performance. The repository already
contains source-bound proteomic signatures, conditional RNA--protein cohort
models, longitudinal protein/phosphosite/program models, graph inference,
composition development, and strict provenance/abstention machinery. The next
scientific gains should come from validation and missing capabilities, with
published models and conventional meta-analysis identified as such.

This is a development roadmap, not evidence that its hypotheses are true or
that every listed phase is implemented. The new
[aggregate cohort-replication lane](cohort-replication.md) performs bounded
summary calculations; it does not itself supply independent cohorts, valid
source-derived SEs, molecular diagnoses, calibrated discoveries, or clinical
utility. All current estimates remain research evidence under their documented
claim ceilings. Governed module contracts and the separate research namespace
remain distinct.

## Scientific ambition and measurable success

The useful lesson from [AlphaFold's primary evaluation](https://www.nature.com/articles/s41586-021-03819-2)
is a well-defined task, strong comparators, blind assessment, reliability
estimates, and testing beyond development examples. Glioma proteogenomics has
different endpoints, much smaller matched patient cohorts, context-dependent
measurements, and no single equivalent of a solved protein structure. There is
no current basis for claiming AlphaFold parity or a comparable scientific
breakthrough.

Choose explicit tasks instead: transport of cohort associations; held-out
protein or phosphosite reconstruction; calibrated uncertainty and abstention;
RNA-native composition against independent references; reproducible regional
heterogeneity; longitudinal transition prediction; and ambiguity-aware peptide
or proteoform evidence. A new feature becomes a scientific improvement only
when it beats the relevant frozen comparator on an independent endpoint with
acceptable uncertainty, missingness behavior, and computational cost.

Adult IDH-wildtype glioblastoma, IDH-mutant astrocytoma, and
IDH-mutant/1p19q-codeleted oligodendroglioma need separate declared domains.
Grade, treatment history, recurrence, anatomical region, molecular status,
assay, and specimen provenance must travel with the analysis. Pediatric
diffuse glioma requires its own support evidence. The
[WHO CNS5 author summary](https://pmc.ncbi.nlm.nih.gov/articles/PMC8328013/)
supports these distinctions; a bulk-protein signature cannot supply a missing
molecular diagnosis.

## Phases and completion gates

The phases are ordered by evidence dependencies, not fixed calendar promises.
Source audit, interface work, and visualization can proceed in parallel where
they do not use validation outcomes for model selection. Each phase retains
failed candidates and negative comparators in its evidence record.

| Phase | Deliverable | Gate for a stronger research claim |
| --- | --- | --- |
| 1. Independent cohorts | Compatible aggregate effects, explicit independence, source comparison explorer | Audited source extraction and frozen external benchmark; calculator success alone is insufficient |
| 2. Calibration | Empirical-null checks, valid effect uncertainty, dependence-aware multiplicity | Prespecified null error and interval-coverage targets pass across relevant regimes |
| 3. Independent perturbation evaluation | Computation against existing held-out perturbation evidence | Improvement over simple observational baselines on an independent, context-matched endpoint |
| 4. Single-cell and spatial | Donor-aware RNA composition and genuine coordinate-aware protein/context views | Held-study/donor/section validation with independent annotations and honest resolution |
| 5. Longitudinal multiview | Patient-grouped recurrence/transition evidence with modality ablations | Incremental external benefit over protein-only and simple transition baselines |
| 6. Proteoforms | Ambiguity-preserving peptide-to-isoform/PTM evidence | Identification and localization error control plus independent reproducibility |
| 7. Scale and pretraining | Versioned distributed data/training/evaluation pipeline | Transfer gains over compact baselines, leakage audit, and measured cost/accuracy curves |

### Phase 1: multi-cohort replication and evidence exploration

Prerequisites are version-specific source manifests, compatible reuse terms,
explicit participant grouping, matched assay interpretation, and a fixed
estimand. The initial practical benchmark is adult IDH-wildtype GBM; extending
to other gliomas is a separately evaluated support-domain change.

[Wang et al., 2021](https://pmc.ncbi.nlm.nih.gov/articles/PMC8044053/) reports
99 treatment-naive GBMs. The existing conditional-association fitter resolves
96 patient groups with common CNV/RNA/protein measurements; those counts must
retain their different meanings. [Liu et al., 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11337243/)
reports 228 tumor specimens from an independent high-grade glioma cohort,
including recurrence. It is a candidate external source, subject to exact
case/processing audit and disease-specific filtering. A specimen count cannot
substitute for an independent participant count.

Implement per-source adapters that derive a prespecified compatible effect
and its SE, preserving source normalization, missingness, grouping, and
covariate definitions. The current CPTAC conditional coefficient is on source
axes; its bootstrap percentile intervals do not automatically admit a
standardized-coefficient/SE conversion. Historical data must not be normalized
using held-out outcomes or validation-cohort labels. Pin PDC study UUID
versions as well as readable study IDs; the latter default to the latest
version in the [official API](https://pdc.cancer.gov/pdc-docs/api-documentation).

The evidence explorer should display forest plots, cohort coverage and
abstention, random/fixed summaries, nominal interval labels, heterogeneity,
prediction-interval assumptions, leave-one-out influence, BH and BY values,
and source/profile digests. Comparison of incompatible scales should fail
before pooling. The UI must distinguish synthetic examples, caller-declared
summaries, internally evaluated source models, and independent validation.

Release gates are an independently checked effect/SE extraction oracle;
documented disjoint participants; a frozen feature family and contrast;
matched source-held-out baselines; interval and effect-direction reporting;
replay/tamper checks; and a clearly labeled source-held-out result. A positive
meta-analysis mean alone does not establish predictive transport or mechanism.
Start on a workstation; parsing and robust per-gene fitting can use a CPU batch
queue. The bounded aggregate engine needs no GPU.

### Phase 2: calibration, selection, and uncertainty

Prerequisites are the exact estimand and sampling structure from phase 1,
source-level complete/missing/censored states, and access to intermediate
measurements inside controlled fitting boundaries. Prespecify empirical error,
coverage, and computational budgets before running validation.

Develop synthetic null and heterogeneous-effect simulations with known truth;
patient-blocked resampling; sensitivity to batch/purity/lineage covariates;
and conditional-null procedures appropriate to the nuisance structure.
Shuffling RNA independently of CNV changes their dependence and can test the
wrong conditional question. Model-dependent permutation or conditional
randomization methods need an explicit exchangeability/generative assumption
and a falsifiable validation plan.

Compare normal/DL inference with better small-cohort uncertainty estimators
where justified, rather than assuming a zero heterogeneity estimate is
certainty. Evaluate nominal interval coverage by k, unequal precision,
heterogeneity, skew, and standard-error misestimation. Model biological
features' dependence when assessing multiple testing; BY handles arbitrary
dependence only when the marginal p-values are valid. Missing hypotheses stay
inside the prespecified family. No method can repair outcome-selected
families or fabricated SEs merely by adjusting p-values.

Assess observed-data and missingness sensitivity separately. LFQ detection
can depend on intensity, as demonstrated by
[Li et al., 2023](https://pubmed.ncbi.nlm.nih.gov/37067487/); a model justified
for LFQ is not automatically valid for TMT-normalized data. Point imputation
must not masquerade as measured support. Report abstention/coverage alongside
accuracy and evaluate uncertainty under the same missingness regimes that
will occur at use time.

Release gates are prespecified empirical type-I-error and interval-coverage
targets with Monte Carlo uncertainty; valid clustered sampling; multiplicity
tests under correlated features; and source-held-out uncertainty diagnostics.
Numerical thresholds must be chosen for the task and locked before testing,
not invented after seeing an attractive curve. Use parallel CPU jobs with
independent deterministic seeds and recorded replicate counts; adaptive Monte
Carlo stopping requires its own valid stopping rule.

### Phase 3: evaluation against independent perturbation evidence

This phase uses existing, admitted computational datasets. It does not require
designing biological systems, new laboratory perturbations, or treatment
recommendations. Prerequisites are an external perturbation dataset with
documented provenance, compatible cellular context, dose/time metadata when
relevant, feature mapping, endpoint, and a test partition untouched by model
selection.

Ask whether observational programs or graph-based predictions correspond to
independently measured molecular responses. Evaluate direction, ranked
response, held-out reconstruction, and uncertainty against intercept,
expression-only, equal-marker, pathway-membership, and simple linear baselines.
Hold entire donors, models, perturbation families, and studies out where
appropriate. Shared training data or published signatures must not leak into
the claimed independent test.

Release gates are context-specific external improvement with uncertainty,
measurement/topology/source ablations, negative controls, and explicit
out-of-context abstention. Association with a perturbation endpoint is not
proof of the causal effect of a proposed patient intervention. A negative
result constrains the model's interpretation instead of being discarded.
Small tasks use CPU batches; GPU work is justified only after a compact
baseline and learning-curve audit demonstrate a need.

### Phase 4: single-cell and spatial resolution

Build on the existing GBmap source-admission/composition work and its
donor/study reconciliation rather than creating a duplicate deconvolution
lane. Its research maturity must be read from its current profile and evidence;
a source-admission document alone does not qualify a fitted model.
Prerequisites are licensed references, cell/donor/study crosswalks, count-native
RNA semantics, independent lineages/annotations, and support for uncommon or
out-of-reference cell types.

RNA-based lineage fractions require held-study and held-donor evaluation with
uncertainty and reference-omission tests. Simulated mixtures supply known-truth
algorithm checks, but do not replace independently measured tissue
composition. Protein marker concordance must remain separate from RNA cell
fractions unless a protein-native mixture model receives its own evidence.
[Neftel et al., 2019](https://pmc.ncbi.nlm.nih.gov/articles/PMC6703186/)
supports heterogeneous malignant programs; bulk program scores do not identify
individual cells or spatial coordinates.

For genuine spatial inputs, preserve section/region coordinates, assay
resolution, segmentation uncertainty, registration, and patient hierarchy.
Implement neighborhood enrichment, spatially constrained nulls, matched-region
RNA/protein concordance, and regional heterogeneity with patient-level
uncertainty. Treat spots, pixels, and cells as dependent observations rather
than thousands of independent patients. Avoid interpolating unmeasured
proteins into apparently observed heatmaps.
[Greenwald et al., 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11088502/)
is a primary spatial glioma reference; its RNA/protein observations do not
license spatial claims from unrelated bulk cohorts.

Release gates are donor/section-disjoint external evaluation, spatial-null
calibration, independent annotation agreement, explicit resolution/missingness,
registration sensitivity, and unsupported-context abstention. Visuals can
include linked tissue views, measured/predicted toggles, neighborhood graphs,
and uncertainty layers. Use sparse CPU processing and blockwise I/O first;
GPU segmentation or representation learning is a separate admitted component
with its own evaluation.

### Phase 5: longitudinal multiview transitions

Prerequisites are verified patient/timepoint lineage, sampling region,
treatment-history metadata, assay-specific reference semantics, and paired
support. The repository already has longitudinal protein, phosphosite,
Neftel-program, Reactome, and participant-set lanes; integration must not count
the same cohort/model multiple times as independent confirmation.

Extend them through external paired cohorts, hierarchical patient/site
evaluation, time-aware baselines, and view-specific missingness. Fit
normalization, hyperparameters, modality weights, and uncertainty inside nested
patient-grouped folds. Compare protein-only, phosphosite-only, equal-weight
fusion, and learned fusion on exactly the same held-patient support. Reference
compatibility and parent-protein adjustment are prerequisites for interpreting
relative phosphosite changes; abundance changes do not establish occupancy.

Preserve the repository's documented negative fusion feasibility result:
phosphosite addition did not improve its evaluated protein baseline. A new
fusion architecture must beat that baseline on a new frozen test; increased
model complexity is not evidence of added information. Report informative
missingness and follow-up selection rather than assuming observed recurrence
pairs represent all patients.

Release gates are independent paired-cohort benefit, patient-clustered
uncertainty, modality and reference ablations, censoring/support tests, and
honest failure when complementary views add no value. Transition concordance
is not a prognosis, recurrence hazard, or treatment-effect estimate. CPU batch
work is sufficient for small dictionaries; use GPU sequence models only with
enough independent longitudinal groups and a demonstrated learning-curve gain.

### Phase 6: proteoform and isoform evidence

Prerequisites are versioned sequence/search-space references, peptide-level
identification evidence, search-space-specific uniqueness, explicit protein
groups, PTM localization evidence, assay detection limits, and matched genomic
coordinates where used. Whole-gene RNA/protein associations cannot supply
missing isoform or modification identification.

Prioritize an ambiguity-preserving peptide-to-protein/proteoform evidence
graph; distinguish shared from discriminating peptides; preserve alternative
assignments and composite phosphosite rows; and propagate identification,
localization, quantification, and missingness uncertainty separately. A
single ambiguous peptide cannot be promoted to a unique proteoform. Expansion
of sequence hypotheses needs search-space-aware error control; novel sequence
evidence is a detection claim requiring independent confirmation, not a
functional claim.

Evaluate gene-collapsed, protein-group, and ambiguity-aware models on
prespecified held-out spectra/runs and independent cohorts with appropriate
grouping. Release gates are independently checked target-decoy/error-control
oracles, discrimination/localization support, false-positive stress cases,
replicate reproducibility, and demonstrated benefit without inflated error.
Proteoform abundance, complex assembly, binding, and biochemical activity are
distinct claims. Large spectral searches need batched CPU or justified GPU
workers and bounded reference storage; the search index and reference hashes
must be reproducible.

### Phase 7: scale, distributed execution, and training distribution

Prerequisites are tasks that already outperform compact baselines, enough
independent source cohorts for learning curves, admitted data/model terms,
and a cohort-overlap ledger. A collection of millions of cells, spectra, or
spatial pixels does not create millions of independent glioma patients.
Training on many modalities does not resolve a small matched-patient sample.

Introduce versioned object storage, content-addressed partitions, streaming
adapters, deterministic work plans, resumable checkpoints, resource limits,
failure replay, and reproducible model registries. Partition by cohort and
participant before derived objects are generated. Audit overlap across public
releases, related papers, reused controls, pretreatment/recurrent specimens,
and pretraining/evaluation sources. Keep a frozen, independently curated test
set with temporal/site holdouts where possible.

Only then evaluate broad proteomics pretraining, domain adaptation, or
multimodal representation learning. Record source and target tasks, training
distribution, model size, data volume, optimization budget, calibration,
out-of-distribution coverage, and per-cohort errors. Compare with source-locked
signatures, ridge/Huber models, simple shared-factor models, and parameter-
matched ablations. A pretrained model must show additional independent benefit
over those baselines, not merely reconstruct its own training distribution.

Release gates are reproducible independent transfer, useful calibration and
abstention, source/domain ablations, scaling curves, and an operational
cost/latency/memory envelope. Distributed GPU training is contingent on those
gates and a resource estimate; no particular cluster size or foundation-model
success is promised. Serving must expose model/reference version, input
support, uncertainty, and provenance rather than hiding limited evidence behind
a categorical answer.

## Compute classes and resource evidence

These are planning classes, not measured hardware requirements or budgets:

| Class | Appropriate work | Required resource evidence before scale-up |
| --- | --- | --- |
| Workstation CPU | Aggregate meta-analysis, strict validation/replay, small gene panels, UI | Peak memory, wall time, byte limits, deterministic numerical agreement |
| CPU batch workers | Workbook/reference ingestion, patient bootstraps, null simulations, robust per-feature fits | Per-task memory/time, streaming behavior, checkpoint cost, replicate convergence and failures |
| Single GPU | Evaluated image/count/representation models with CPU baselines | Batch-size/memory curve, held-out gain, seed variability, inference latency, numerical reproducibility |
| Distributed storage/compute | Broad admitted pretraining or large spatial/spectral collections | I/O/communication profile, scaling efficiency, restart recovery, total cost, training/test overlap audit |

Choose compute from measured workload and learning curves. Do not buy scale
to compensate for an unspecified estimand or a failed independent baseline.
Report preprocessing and source-ingestion costs separately from the often
small aggregate analysis runtime.

## Unproven hypotheses and falsification criteria

These are candidate research questions, not novel discoveries or commitments
that a positive result will emerge:

| Hypothesis | Required comparison | Evidence that would limit or reject it |
| --- | --- | --- |
| Composition-aware conditional RNA--protein associations transport better across GBM cohorts | Same prespecified model/estimand with and without admitted composition covariates, external cohort held out | No incremental held-out benefit, unstable direction, or worse calibrated uncertainty |
| Evidence-weighted protein/pathway programs improve reconstruction across institutions | Frozen equal-marker, global-factor, and robust linear baselines on matched support | Gain disappears on study holdout or is driven by a single cohort/member |
| Complementary longitudinal modalities add information beyond protein alone | Protein-only and independently tuned multiview models on the same held-out patients | No incremental gain, missingness-driven advantage, reference incompatibility, or poorly calibrated intervals |
| Ambiguity-aware proteoform evidence improves reproducibility over gene collapse | Error-controlled peptide/proteoform evaluation and independent replicates | Inflated false identifications, unresolved localization, or no reproducible improvement |
| Broader pretraining transfers useful information into glioma tasks | Independent target cohorts, fixed compute, compact/model-size-matched baselines | Gains vanish after overlap removal, are confined to training cohorts, or fail the cost/uncertainty criterion |

Before each test, lock the endpoint, comparison, acceptance margin, uncertainty
method, feature family, split structure, and reporting policy. If the smallest
meaningful improvement cannot be estimated with available independent cohorts,
record that evidence limit and choose a narrower task. The absence of a
positive result must remain visible in the platform.

## Definition of a completed phase

A phase is complete only when its scientific estimand, strict input/output
contracts, admitted source/version evidence, executable implementation,
meaningful numerical oracles, independent benchmark where claimed,
uncertainty/ablation results, negative cases, compute measurements, and replay
receipt are reviewable together. Unit tests prove behavior under selected
cases; they do not supply independent biological validation.

Visual sophistication should make those distinctions easier to inspect.
Linked forest plots, coverage funnels, observed/predicted spatial layers,
paired-transition views, and ambiguity graphs are useful when they expose
their actual evidence and uncertainty. A dense network, inferred cell map,
or uncalibrated score must not imply a result that the data have not measured.
