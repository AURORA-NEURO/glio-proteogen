# GBmap source admission for donor-aware GBM composition inference

Status: **source admitted for private offline development only; no fitted artifact,
runtime model, or HTTP claim exists yet**.

The next uncovered M14 scientific responsibility is genuine multi-lineage
composition inference. The current Neftel facade reports bulk-protein program
concordance, and GBMPurity reports one malignant-cell fraction. Neither is a
multi-lineage deconvolution model.

The selected fitting source is the fixed
[GBmap Zenodo record](https://zenodo.org/records/6962901), DOI
`10.5281/zenodo.6962901`. Its `scarches_core_GBmap.h5ad` artifact is
8,975,644,082 bytes with source MD5
`308f143ba384bd9a8acb0fbf2ea005fc`. The record and the
[peer-reviewed GBmap publication](https://doi.org/10.1093/neuonc/noaf113) are
CC BY 4.0. The fitting artifact contains 338,564 cells, 5,000 selected genes,
raw counts in `layers["counts"]`, donor labels in `patient`, study labels in
`author`, and 20 harmonized `CellID` labels. The current
[CELLxGENE mirror](https://cellxgene.cziscience.com/collections/999f2a15-3d7e-440b-96ae-2c806799c08c)
is metadata corroboration, not the byte authority.

The donor-count discrepancy is now split by artifact rather than guessed away.
The paper prose and Figure 1 say 109 patients, but the final
[Supplementary Table S1](https://pmc.ncbi.nlm.nih.gov/articles/instance/12526130/bin/noaf113_suppl_supplementary_tables_s1-s5.xlsx)
lists 16 study counts that sum to 110 and explicitly reports 110 core patients
and 338,564 cells. The official
[CELLxGENE dataset metadata](https://api.cellxgene.cziscience.com/curation/v1/collections/999f2a15-3d7e-440b-96ae-2c806799c08c/datasets/c888b684-6c51-431f-972a-6c963044cef0)
also exposes 110 unique donor categories for core dataset
`c888b684-6c51-431f-972a-6c963044cef0`, version
`861acfd8-25f0-418b-a445-aa96da232827`.

A bounded read-only HDF5 metadata audit of the byte-authoritative Zenodo file
found a different, earlier representation: its `obs/patient` field contains
113 used raw categories. Three are source samples `PW032-701`, `PW032-702`, and
`PW032-712`; the pinned preprocessing notebook directly supports grouping all
three under donor `PW032`. That evidenced three-to-one mapping reduces 113 raw
categories to 111 grouped donors. `R4` and `R4 n.c.` are the remaining mismatch
against the separately curated 110-category CELLxGENE asset. This identity is
now resolved from the original Pombo study rather than inferred from the target
count. Its official
[Nature Reporting Summary](https://static-content.springer.com/esm/art%3A10.1038%2Fs41593-020-00789-y/MediaObjects/41593_2020_789_MOESM2_ESM.pdf)
enumerates recurrent patients as R1–R5 and lists only patient R4. In official
[Supplementary Table 1](https://static-content.springer.com/esm/art%3A10.1038%2Fs41593-020-00789-y/MediaObjects/41593_2020_789_MOESM3_ESM.xlsx),
the `R4 n.c.` assay row immediately follows R4 and leaves every donor-level
clinical field blank, matching the table's handling of an additional frozen
R2 biospecimen. EGA retains
[`R4 n.c.`](https://metadata.ega-archive.org/samples/EGAN00002820637) and
[`R4`](https://metadata.ega-archive.org/samples/EGAN00002820638) as separate
sample objects. The reviewed crosswalk therefore preserves both raw source
labels but groups both to donor R4. The primary sources do not define `n.c.`,
so the suffix remains opaque rather than being expanded or reinterpreted.

The discrepancy is also temporal and representational, not evidence for an
undocumented computational collapse. The official 2022 preprint source
described 110 patients. In the commit-pinned
[core preprocessing notebook](https://github.com/ccruizm/GBmap/blob/43bb27421214d902229f2a9d5ffbe67cca27b9ec/notebooks/01_building_core_GBmap_reference/01_data_import_and_preprocessing.ipynb?plain=1#L4107-L4136),
the final metadata merge deduplicates cells, not patients, and no global
cross-study donor-collapse table is applied. Two explicit within-source ID
repairs—Zhao `PW031` to `PW032` and Bhaduri `TQ` to `SF11247`—occur before the
core object is assembled. The code guard compares category sets rather than API
presentation order and fails closed on collection, dataset, version, schema,
cell count, asset, category count, category vocabulary, or crosswalk drift.

The Zenodo file also contains 17 used `obs/author` categories, not 16 directly
usable study groups. `Neftel2019_10x` and `Neftel2019_smart` are technical
batches of the same biological study and share six donor categories. The
source-locked study crosswalk maps both to `Neftel2019`; splitting on raw
`author` would leak those donors between study folds. The exact 20 used
`CellID` labels are preserved without inferred collapse: AC-like, Astrocyte,
B cell, CD4/CD8, DC, Endothelial, MES-like, Mast, Mono, Mural cell, NK,
NPC-like, Neuron, OPC, OPC-like, Oligodendrocyte, Plasma B, RG, TAM-BDM, and
TAM-MG.

The exact admission record is
[`sources/gbmap-core-zenodo-6962901.yaml`](sources/gbmap-core-zenodo-6962901.yaml).
The exact 8,975,644,082-byte artifact now matches the official MD5 and the
independently recomputed SHA-256
`sha256:cb48db2e31299b41d2fe2b6004fadbabe49957bf7d6d72396139db12366ecd8a`.
The canonical fingerprint receipt is bound by
`sha256:b46e9e32d2d6d70459d8fcb3d2c4e725fde4503e96023809decdd463f19124b2`.
The fingerprint tool itself verifies byte identity only, so its
`admission_granted` field remains false. A subsequent exact structural preflight
reverified the 113→110 donor crosswalk, 20-label vocabulary, 17→16 study
crosswalk, 338,564 cells, and locked 196,660,428-entry CSR matrix. The reviewed
admission-basis preflight receipt is
`sha256:f3556ae988b64aa1c1f8ff447a8a5004c4a7b8ffe667203d24fe5b32b2e2b3af`.
After the profile recorded that decision, the exact source was replayed under
the new semantic lock; the current validating receipt is
`sha256:c0121ef9e608c54a619d7f93292437bfdbc3b934b8f507f1c0bae1af103787f8`.
Both runs share extraction receipt
`sha256:787d1fa63b6bea7848c3353ee97d15195a296ff216be57b3eb3266525e3ccd15`.
That evidence admits the exact source for private offline development only. It
does not admit the raw H5AD into the repository, a fitted artifact, a runtime,
or an API.

### Bounded local fingerprint receipt

Keep the H5AD outside the repository and run the repository-safe fingerprint
tool from the repository root:

```powershell
uv run --frozen python tools/capture_gbmap_source_admission.py `
  --source "D:\private-gbmap\scarches_core_GBmap.h5ad" `
  --output "D:\private-gbmap\gbmap-source-admission-receipt.json"
```

The command uses the production byte-length, Zenodo MD5, source identity, and
repository boundary compiled into the tool; none is a caller override. It
rejects an H5AD stored anywhere under the repository, reads the stable regular
file once to calculate both MD5 and SHA-256, writes no H5AD bytes, and emits
compact canonical JSON to stdout and, when requested, the exact same bytes to
`--output`. The receipt contains no local path, cell material, donor
identifiers, or raw content. Output publication writes and `fsync`s a private
temporary file in the destination directory, atomically creates the final path
without replacing an existing file, and cleans the temporary file on failure
or interruption. An identical existing receipt is an idempotent replay; a
different or unreadable existing output is never overwritten. Filesystem and
fingerprint failures are reported without echoing local paths or chained
path-bearing exceptions.

After a separate reviewer or independent tool has recomputed SHA-256, compare
that value explicitly:

```powershell
uv run --frozen python tools/capture_gbmap_source_admission.py `
  --source "D:\private-gbmap\scarches_core_GBmap.h5ad" `
  --reviewed-sha256 "sha256:<64-lowercase-hex>" `
  --output "D:\private-gbmap\gbmap-source-reviewed-receipt.json"
```

`review_match` becomes true only for an exact canonical digest match. A
supplied mismatch is still represented in the stdout receipt but exits with
status 3 so automation fails closed. With or without a match,
`admission_granted` remains false: this tool does not parse or extract H5AD
content, run the fitter, mutate the source manifest, create a fitted artifact,
or authorize an API/runtime. Full extraction, structural revalidation,
scientific evaluation, license review, and a separate source-admission change
remain required.

### Private structural preflight

Before starting hierarchy training, maintainers should run the exact structural
preflight against the independently reviewed H5AD:

```powershell
uv run --frozen --group source python tools/preflight_gbmap_development_candidate.py `
  "D:\private-gbmap\scarches_core_GBmap.h5ad" `
  --reviewed-sha256 "sha256:<64-lowercase-hex>" `
  --output "D:\private-gbmap\gbmap-development-preflight-receipt.json" `
  --acknowledge-development-only `
  --acknowledge-sha256-independently-reviewed
```

This maintainer-only command reuses the production byte lock, outside-repository
and non-reparse source guard, same-handle two-pass extraction, reviewed donor and
study crosswalks, and exact label taxonomy. It builds the deterministic
whole-study and within-study-donor split plan, then stops before marker
selection or any hierarchy fit.

The immutable receipt contains the existing deidentified extraction and split
receipts, development-profile and training-configuration digests, per-fold
non-identifying dimensions, and conservative hierarchy-task upper bounds. The
upper bounds are planning dimensions, not evidence that every label will pass
fold-local marker selection or that any fit will converge. Explicit false flags
prove that hierarchy training did not run and that no model, parameters,
artifact, runtime, HTTP route, or CLI surface was admitted.

The production run produced 1,168 donor/lineage aggregate records and 21
validation folds, of which 20 are evaluable. Fold support reduces the exact
hierarchy-work upper bound to 739 fits: 720 validation fits and 19 possible
final lineage fits over four shrinkage candidates. One within-study donor fold
abstains. These are source-derived planning facts, not fitted-model results.

The receipt contains no source path, donor identifiers or hashes, donor
profiles, aggregate-content digest, feature identities, count vectors, cell
material, or raw content. Transient aggregates and donor partitions remain in
memory and are discarded. Publication uses a same-directory fsynced temporary
and an atomic no-overwrite link. Repeating the command against an identical
verified receipt is idempotent; different existing bytes are never replaced.
Filesystem, HDF5, provenance, projection, and publication errors are reported
through a stable message that does not echo local paths or donor material.

### Private resumable hierarchy tasks

After a structural preflight succeeds, maintainers can derive and inspect the
exact post-selection validation schedule without starting a hierarchy fit:

```powershell
uv run --frozen --group source python tools/run_gbmap_hierarchy_tasks.py `
  "D:\private-gbmap\scarches_core_GBmap.h5ad" `
  --reviewed-sha256 "sha256:<64-lowercase-hex>" `
  --preflight "D:\private-gbmap\gbmap-development-preflight-receipt.json" `
  --run-directory "D:\private-gbmap\gbmap-hierarchy-run" `
  --dry-run `
  --acknowledge-development-only `
  --acknowledge-sha256-independently-reviewed
```

The private run directory must remain outside the repository and use only
ordinary non-reparse ancestors. A dry run re-extracts the exact locked H5AD,
reconciles the complete preflight receipt, deterministically rebuilds every
split and fold-local marker selection, and atomically publishes an immutable
run manifest. It reports the exact task count without calling the hierarchy
solver. Tasks exist only for `(fold, shrinkage, modeled label)` coordinates
that are evaluable in the split receipt and survive fold-local stable-marker
selection; an upper-bound preflight count never fabricates work for an
unsupported lineage.

Run a bounded lexical prefix of pending work by omitting `--dry-run`:

```powershell
uv run --frozen --group source python tools/run_gbmap_hierarchy_tasks.py `
  "D:\private-gbmap\scarches_core_GBmap.h5ad" `
  --reviewed-sha256 "sha256:<64-lowercase-hex>" `
  --preflight "D:\private-gbmap\gbmap-development-preflight-receipt.json" `
  --run-directory "D:\private-gbmap\gbmap-hierarchy-run" `
  --max-tasks 4 `
  --acknowledge-development-only `
  --acknowledge-sha256-independently-reviewed
```

Each invocation re-extracts and re-prepares the source instead of persisting
private aggregates. Before skipping any task, it strictly parses every
existing canonical shard, verifies the manifest/task/source/profile/config/
split/feature-axis/training-matrix bindings, and replays the selected feature
axis, training-matrix digest, and held-evidence dimensions against the newly
derived in-memory data. Missing tasks are executed in fixed lexical order up
to `--max-tasks` (default 1, maximum 256).

Checkpoint filenames contain both the input-task digest and output-content
digest. Manifest and checkpoint publication use fsynced same-directory
temporaries plus atomic no-overwrite links; an identical publication is
idempotent, while a changed manifest, duplicate task, unexpected shard,
noncanonical JSON, forged digest, cross-run shard, or inconsistent numerical
result fails closed. A checkpoint contains only a deidentified per-lineage held
NLL, held record/study counts, convergence/objective/KKT diagnostics, public
task coordinates, and semantic digests. Fitted study/global signatures,
concentrations, and other reusable model parameters are deliberately discarded
after scoring. It contains no source path, donor identifier or donor hash,
donor profile, feature identity, count matrix, aggregate-content digest, cell
material, or raw source content.

This stage covers validation hierarchies only. It neither schedules final
lineage fits nor selects a shrinkage candidate, builds a final model, emits an
artifact, mounts a runtime, or changes an HTTP/public-CLI surface. Every
manifest, shard, and batch receipt retains explicit false permission flags.
A later final-fit stage must independently enforce lineage validation-coverage
gates before using these checkpoints.

### Private offline development fit

Do **not** run the current one-shot command at full production size yet. It has
no task checkpoint/resume layer and discards model parameters after emitting a
receipt. The 739-fit preflight ceiling remains operationally too expensive and
fragile until resumable, content-bound task execution and the remaining exact
optimizer improvements are implemented. The command below documents the
development boundary and remains useful for bounded fixtures.

After the full-file SHA-256 has been independently recomputed and reviewed, a
maintainer may run the source-locked extractor and development trainer in one
private process:

```powershell
uv run --frozen --group source python tools/fit_gbmap_development_candidate.py `
  "D:\private-gbmap\scarches_core_GBmap.h5ad" `
  --reviewed-sha256 "sha256:<64-lowercase-hex>" `
  --output "D:\private-gbmap\gbmap-development-fit-receipts.json" `
  --acknowledge-development-only `
  --acknowledge-sha256-independently-reviewed
```

Both acknowledgements are mandatory. The command constructs the repository's
fixed Zenodo byte/MD5 lock, production H5AD recipe, reviewed 113→110 donor
crosswalk, 17→16 study crosswalk, and 20-label taxonomy; SHA-256 is the only
reviewer-supplied lock field. It then calls the existing exact extractor and
development trainer directly, without a subprocess, service, API route, or
public CLI registration.

The output is a new, atomically published canonical JSON file containing only
the deidentified extraction receipt, deidentified validation-split receipt,
and development training summary. It never contains the local source path,
cell/barcode material, donor identifiers or hashes, donor profiles, transient
aggregates, stable-gene identities, fitted signatures/concentrations, or the
candidate model. Existing outputs are not overwritten. The model remains
in-memory with `production_artifact_permitted=false` and
`runtime_mount_permitted=false`, and is discarded when the process exits.

This run is deliberately non-resumable. The extractor performs two complete
hash passes over the approximately 9 GB file around structural extraction, and
training retains its bounded aggregate and fold state only in memory. An
interruption, source mutation, hash mismatch, HDF5 error, failed support gate,
or numerical nonconvergence publishes no receipt; restart from the unchanged
source. The retained receipt is development evidence, not source admission,
external validation, a fitted artifact, or permission to mount a runtime.

## Grouped validation and complete-task reduction

The current development profile binds
`gbmap-within-study-eligible-donors/2.0.0`. Within-study holdouts use only studies
with at least two eligible grouped donors. Singleton-study donors remain in
training for that family and are tested in their existing whole-study holdout.
The count-only `within_study_holdout_coverage(plan)` ledger distinguishes those
training-only groups from donors held exactly once. It checks partition and
study consistency without retaining donor identifiers or hashes. All original
lineage support requirements and the five accepted donor-fold requirement remain.

Production marker ranking now uses only the pinned 4,923 unique model-eligible
HGNC source coordinates. The complete 5,000-column raw extraction axis is retained.
Admission occurs before candidate scoring, marker caps, feature union, background
construction and fitting. Direct hierarchy fitting requires the bound aggregate
reference and rejects an unadmitted selected coordinate. Generic caller-owned
references keep their own explicitly supplied feature universe.

`run_gbmap_hierarchy_tasks.py --workers 1|2|3|4` can evaluate independent tasks in
shared private memory. The default remains one worker. Source verification and
checkpoint publication remain on the owning thread in lexical task order, even
when fits finish out of order. Parallel execution retains the same tasks,
numerical controls, immutable checkpoints, source guards and resume checks.
No donor profiles are serialized for workers. Thread count is a scheduling choice,
not a new fitting or statistical policy. Invalid arguments produce a sanitized
error before source access and do not echo private paths or malformed values.

`tools/reduce_gbmap_hierarchy_tasks.py assess <run-directory>` checks the sealed
preparation inventory without reading the H5AD. It reports whether the prepared
folds could satisfy the unchanged three whole-study and five donor-fold gates;
potential feasibility does not establish numerical success. `reduce` additionally
requires `--source`, `--reviewed-sha256`, `--preflight`, and both development/review
acknowledgements. It re-extracts the exact source and validates runtime bindings
through the existing dry-run executor before reducing the complete task set.
Checkpoint and manifest snapshots must remain identical across that replay.
Missing, duplicate, extra, changed or unbound tasks cannot yield a selection.

The reducer computes equal-lineage fold scores, equal-fold family scores and an
equal mean of the two validation families. Any failed lineage task abstains that
candidate's entire fold. Only candidates satisfying both family gates can be
selected; exact ties choose the smaller shrinkage. All source labels retain an
explicit validation-coverage disposition. The final-lineage policy
`gbmap-final-lineage-validation-coverage/1.0.0` requires a production lineage's own
three whole-study and five donor-fold successes from the selected candidate.
Those checks precede final feature/background construction and remain conjunctive
with full-source donor, study, marker and convergence gates. Another candidate's
successful fits or another lineage's coverage cannot provide missing support.

Optional `--output` publishes a new canonical private receipt outside the run
directory and repository, without replacing different existing bytes. `verify
<receipt>` checks saved integrity and the current method; it does not replay the
source. A source-replayed task reduction is still signature-prediction evidence,
not mixture accuracy, unknown-mass calibration or a released model artifact.

GBmap includes different sequencing platforms. Compatibility field names such as
`total_umis` represent admitted native raw-count mass here, not a guarantee of
uniform unique-molecule measurement across platforms. The upstream 5,000-gene
universe and harmonized labels were selected on the core before our splits.
Validation is conditional on those upstream choices; annotations incorporating
computational cell typing and inferred CNV are not independent histologic truth.
The exact core asset must not be replaced by the newer extended atlas or mirror
without separate source, overlap and independence review.

## Feature preparation diagnostics

The additive `gbmap_development_diagnostics` namespace explains preparation under
the unchanged fitter. It retains every one of the 20 public source labels in the
full reference and each original validation partition. Its support counts
separate eligible donor/label aggregates from aggregates failing only the cell
threshold, only the native count-mass threshold, or both. Comparator counts
separate same-donor comparisons, the original same-study fallback and missing
comparators. An unavailable selector result remains null across labels, rather
than being replaced by zero passing markers.

For completed selection, the receipt records individual gate pass counts and a
fixed cumulative order: strict label winner, enrichment, donor stability, study
stability, detection and label margin. This order describes attrition; it does
not establish which gate caused a biological difference. The original selector
still includes all usable labels in competition and in the label/union caps,
including labels that later fail preparation support. Counts reconcile with the
original selector, and actual original fold preparation is checked without
calling a hierarchy or final fitter. Selector-wide union retention remains
distinct from the feature union entering a prepared fold.

Full-source held counts and preparation eligibility are not applicable. Those
diagnostics establish neither selected-candidate validation coverage nor final
fit eligibility. No rows, donor/study keys, donor hashes, gene identities,
expression vectors, fitted parameters or reference-content digest are retained.
Excluded source coordinates are not all unresolved mappings; identity admission
can also exclude resolved but nonunique model coordinates.

`tools/audit_gbmap_feature_attrition.py run <source>` requires the independently
reviewed SHA-256, the canonical `--preflight` and both development/review
acknowledgements. It re-extracts the exact source through the pinned reader,
checks fresh structural preflight equality, reconciles the original ordered
fold axis, and keeps the read-only source guard through report construction.
The pure API's caller-supplied profile digest is not authenticated by itself;
the driver supplies and checks the current source/profile context.

Optional `--run-directory` compares the existing immutable manifest's preparation
counts and exact scheduled lineage axis. It does not inspect checkpoints,
replay numerical task matrices, execute fits or reduce validation outcomes.
Optional `--output` publishes canonical bounded aggregate JSON outside the
repository and hierarchy directory, using ordinary verified ancestors and
refusing to replace different bytes. `verify <receipt>` checks saved integrity
and current method/profile bindings, without source replay. The diagnostic
method is separately sealed and does not change the frozen fitting profile,
selection gates, validation tasks or runtime inventory.

## Held-donor count truth

The separate `gbmap_held_mixture_truth` namespace supplies the observed-count
side of a future mixture benchmark. For one original validation fold,
`build_held_mixture_truth` pools every raw donor-label aggregate belonging to
each held donor unit, including aggregates below the reference-fitting floors.
It reconstructs the original split plan before accepting its partitions. No
training donor contributes counts to a held case. Source units outside the
eligible split universe remain explicit in the assignment ledger.

A caller supplies a separate feature-axis and known-label context for each
fold. The planner checks source-axis binding and training-label membership;
it does not authenticate how signatures or selected features were learned.
Reusing a full-source or another fold's learned context would invalidate a
held-out model assessment. The context therefore explicitly retains
`learned_provenance_authenticated=False`.

Each private case retains all 20 public source labels and exact count mass on
both the original feature axis and the selected axis. The corresponding
fractions can differ. A label with original-axis mass but no selected-axis
counts remains unobservable on that selected axis. Zero selected depth causes
an explicit abstention. Reclassifying an omitted label changes its known and
unknown truth allocation without deleting counts or renormalizing the known
population. Private cases retain no donor identifiers. Collection, case and
omission-view objects deny implicit serialization; explicitly retrieved count
arrays remain private. The retained receipt contains aggregate counts and
public labels only.

These are empirical reference pseudobulks, rather than newly measured bulk
specimens. A reviewed donor unit may pool several samples. Neither fraction is
a genome-wide RNA fraction, cell fraction or histologic purity; the pinned
source axis has already undergone feature selection, and its platforms do not
uniformly measure UMIs. Study sampling and enrichment can distort the observed
population proportions, as described in the
[GBmap publication](https://pmc.ncbi.nlm.nih.gov/articles/PMC12526130/).
The planner performs no mixture inference, threshold calibration or accuracy
evaluation. Those stages still require fold-specific fitted signatures and
separately justified concentration and unknown-component penalties.

## Intended model

The implementation will be independently authored. No GBmap repository code,
BayesPrism code, or GBMDeconvoluteR code will be copied.

The offline fitter will estimate donor- and study-shrunk count signatures with
a hierarchical Dirichlet-multinomial model. Feature selection must occur
inside each donor/study training fold and reward cross-donor stability rather
than only differential expression. Runtime inference will optimize a
nonnegative simplex mixture with gene-specific overdispersion and an explicit
unknown/residual component.

Uncertainty and model mismatch will be calibrated with:

- held-donor pseudobulk mixtures;
- whole-study holdouts;
- cell-family omission negative controls;
- synthetic mixture-depth and composition shifts; and
- an independent CC BY 4.0 24-donor
  [Jia et al. glioblastoma cohort](https://figshare.com/articles/dataset/Single-cell_and_spatial_transcriptomic_profiling_of_human_glioblastomas/22434341)
  used only as a robustness stress test.

Only aggregate signatures, dispersion parameters, split receipts, evaluation
summaries, and source/provenance digests may enter the repository. Raw cells,
barcodes, donor-specific expression profiles, and resample assignments may not.

## Claim ceiling

Initial outputs will be `LIMITED` reference-fitted composition weights. They
will not be described as validated histologic fractions, spatial abundance,
treatment response, prognosis, or clinical truth. The GBmap publication notes
that study-specific enrichment strategies make observed cell proportions an
unreliable proxy for actual tumor prevalence; the model must therefore retain
an unknown component and abstain when residual mass or reference mismatch is
too large.

No endpoint may be mounted until the source bytes, fitting profile, held-out
evaluation, artifact license notice, and exact replay fixtures are all bound.

## Implemented source-independent core

The source-independent numerical foundation is implemented under
`src/glio_proteogen/research/gbmap_deconvolution/`. It includes:

- a pinned, offline-only `h5py==3.16.0` extractor for the legacy AnnData 0.7.5
  layout, using one read-only handle, full-file MD5/SHA-256 before and after
  extraction, and no private 9 GB copy;
- exact structural locks for `/layers/counts` CSR shape 338,564×5,000,
  196,660,428 stored `float32` entries, `int32` indices and row pointers, plus
  the external `obs/__categories` vocabularies;
- bounded sparse-row aggregation that rejects nonfinite, negative, fractional,
  overflowing, duplicate-index, explicit-zero, missing-code, or unresolved
  category evidence instead of rounding or imputing it;
- separate digest-bound donor and study crosswalks, including the evidenced
  PW032 three-sample grouping, the R4/R4-n.c. two-sample grouping, and the
  17→16 Neftel batch mapping; and
- a deidentified extraction receipt containing counts and semantic digests but
  no cell barcodes, donor identifiers, donor hashes, donor profiles, or
  transient aggregate-content digest;
- a maintainer-only structural preflight that runs exact extraction and
  leakage-safe split planning without hierarchy training, emits only
  deidentified provenance and task-dimension evidence, and atomically refuses
  to overwrite different receipt bytes;
- a maintainer-only resumable hierarchy executor with an exact dry-run schedule,
  bounded lexical batches, immutable manifests, and content-addressed shards
  that replay against re-extracted training matrices before resume;
- exact immutable donor/label pseudobulk aggregates with canonical source and
  feature-order digests;
- fold-local marker selection using same-donor comparators, cross-study
  fallback, donor/study stability gates, and exact feature-ID tie breaking;
- deterministic whole-study and within-study donor validation plans with
  per-lineage support gates and receipts that retain no donor IDs or donor-ID
  hashes;
- independently implemented Dirichlet-multinomial likelihood, gradient,
  curvature, sampling, and trace verification;
- donor/study-shrunk signature fitting with equal-study global updates,
  bounded concentration estimation, monotone backtracking, cancellation, and
  KKT diagnostics;
- an adaptive-unknown simplex solver that preserves known mass rather than
  renormalizing away unexplained evidence; and
- normalized deviance, Pearson and Aitchison residuals, experimental unknown-mass
  calibration primitives, and curvature-based identifiability diagnostics.

The existing unknown-mass calibration helper does not yet justify nominal
finite-sample coverage. It clamps an adjusted order-statistic rank above the
calibration sample size to the observed maximum. That maximum cannot provide
arbitrarily high requested coverage: the conformal construction instead needs
an infinite upper bound, or the known support bound for explicitly bounded
scores. Its reported specificity is measured on the calibration observations;
that value and a hard-ceiling check do not certify future specificity. See
[Angelopoulos and Bates, Appendix D](https://arxiv.org/html/2107.07511v6#A4).
The hierarchy trainer, task executor and reducer do not call this helper. A
separately versioned correction and held-out calibration assessment are required
before it can support mixture uncertainty claims; the ongoing frozen hierarchy
method is unchanged.

The development trainer connects those components without a shortcut formula.
For every shrinkage candidate it performs marker selection inside each
training partition, fits only eligible lineage hierarchies, scores held
pseudobulks with equal-label/equal-study per-count Dirichlet-multinomial NLL,
and gives the whole-study and stratified held-donor validation families equal
weight. It requires at least three evaluable whole-study folds and five
evaluable donor folds by default, then refits the selected candidate on the
full aggregate reference. Nonconvergence, sparse marker unions, missing held
counts, or inadequate validation cause abstention. The retained training
summary contains no donor IDs, donor-ID hashes, or aggregate-content digest.

The hierarchy kernel uses vectorized, parity-checked DM gradients and diagonal
curvature plus safeguarded bounded Newton updates for concentration. This keeps
the implementation numerically equivalent to the independently tested scalar
DM functions while avoiding per-donor validation inside every optimizer step.

The development profile records `fit_state="development_unfitted"`, AST-binds
these semantics and the metadata reconciliation guard, and sets its expected
fitted-artifact digest literally to
`None`. Model, artifact, runtime, HTTP, and CLI availability are all false, and
`SUPPORTED` output is structurally forbidden. This implementation therefore provides a testable
fitter and inference foundation without increasing the fitted-model inventory
or implying that a completed, validated fitted artifact exists.

## Private development-fit driver

Maintainers may run `tools/fit_gbmap_development_candidate.py` only with an
exact local H5AD path, an independently reviewed canonical SHA-256, and both
explicit acknowledgement flags. The source must remain outside the repository;
the source and every lexical ancestor must be ordinary non-link, non-reparse
filesystem objects. A read-only handle pins file identity during the extraction
and training run, and source identity, lexical containment, and ancestor
identities are revalidated before any receipt can be published.

The driver performs extraction and development training in one private process.
It has no checkpoint or resume mechanism, does not serialize a fitted model,
and is not mounted in the API or public CLI. A failure requires a full rerun
from the unchanged locked source. Its sole durable output is an atomic,
non-overwriting canonical JSON bundle formed by exact allowlisted projections
of the existing extraction receipt, validation-split receipt, and training
summary types. The bundle rejects additional nested fields and reconciles the
source SHA-256/byte length, production taxonomy and recipe digests,
feature-order digest, validation folds, privacy flags, and no-publication gates
before binding the complete projection with a top-level SHA-256 digest.
