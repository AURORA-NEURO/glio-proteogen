# Research protein-inference pipeline (non-governed)

This document describes the executable research lane added on top of the public-
proteomics foundation. It is intentionally not a GLIO-PROTEOGEN production module
and does not widen M03/M04 contracts.

## Computation performed

`run_research_protein_inference` accepts caller-owned mzML and FASTA bytes and applies
one deterministic, auditable path:

1. Decode bounded mzML spectra and retain MS2 spectra only for identification.
2. Digest FASTA entries with trypsin and the declared missed-cleavage and peptide-length
   controls.
3. Score theoretical b/y fragments against observed m/z/intensity arrays using the
   explicit fragment tolerance and minimum matched-ion threshold.
4. Retain every precursor-compatible candidate in a per-spectrum competition receipt,
   including target/decoy/collision counts, winner/runner-up scores, score margin, and a
   canonical candidate digest. The legacy single-winner projection is derived from this
   receipt; lower-scoring contenders are never silently discarded from replay evidence.
5. Perform target/decoy competition and calculate monotone q-values. A spectrum whose
   peptide maps to both target and decoy accessions is recorded as a collision and
   conservatively abstained rather than promoted to either side. PSMs are accepted only
   at the caller-declared q-value threshold.
6. Resolve protein-group candidates from the scored PSMs, including target, decoy, and
   mixed target/decoy collision evidence. Duplicate contenders for one spectrum are reduced to
   one deterministic winner for scoring, while a canonical digest of every contender remains in
   the group summary. Each candidate receives a deterministic max-supporting-PSM score and
   monotone group-level target/decoy q-value. Decoy groups are rejected, mixed groups are retained
   as null-q collision abstentions, and shared-only groups are marked ambiguous before
   quantification. Only target groups passing this second threshold become reportable groups.
   This is transparent group-FDR evidence, not a calibrated protein probability.
7. Aggregate matched fragment-ion intensity for peptides belonging to reportable groups
   and median-normalize within the sample with explicit zero-signal missingness; spectral
   counts remain a separate transparent measure. Every run emits a replay-bound
   quantification receipt containing the arbitrary measurement unit, raw and normalized
   peptide signals, duplicate-observation count, positive/missing counts, raw median,
   normalization target, and scale factor.
8. Quantify each reportable protein group from the median positive unique-peptide
   intensity. Shared signal remains visible, but shared-only groups are explicitly
   non-quantifiable rather than assigned a fabricated protein value.
9. Emit SHA-256 input/evidence/result digests and permit a complete deterministic replay.

## Multi-sample cohort evidence

`run_research_cohort` is the bounded multi-run layer above the single-sample pipeline.
The caller supplies two to 32 independently replayable `ResearchCohortSample` records,
with opaque sample/cohort/replicate identifiers. Every child run must use the same FASTA
digest and search/digestion/quantification configuration; incompatible search spaces are
rejected before a matrix is emitted. External PDC samples can carry a `PdcSourceReceipt`,
which binds the exact selected file to a captured `PdcStudySnapshot`, observed
SHA-256/MD5/size, and the content-addressed `SourceReference`; a caller-provided response
hash alone is not a catalog attestation. The cohort `provenance_policy` is explicit:
`homogeneous` (the default) rejects local/PDC mixing and requires one study/response for
catalog-bound runs, `local_only` rejects catalog receipts, `external_same_study` requires a
receipt for every sample with one study/response, and `mixed_declared` is the opt-in escape
hatch whose mixed source identities remain fully recorded. Receipt fields are retained per
child and remain bound through child result digests, so a file rename, response change, or
source substitution cannot replay as the same cohort.

The result is a deterministic sample-by-protein-group matrix. Groups are the union of
reportable child groups; an absent or non-quantifiable child cell is represented as JSON
`null`, never zero or imputed. Per-group QC reports observed/missing counts, missingness
rate, median intensity, and median absolute deviation. Per-sample QC reports spectra,
accepted PSMs, quantified/missing groups, target/decoy/collision winners, and precursor
error diagnostics. Sample order is canonicalized by opaque sample ID, and the complete
matrix, QC, child digests, source declarations, and configuration are replay-verified.
The locked release evidence carries these projections per evaluator scenario, and the
verifier compares the recorded matrix, null cells, QC, source provenance, configuration,
and child/result digests to a fresh run; counts and a fixture hash alone are insufficient.

### Independence-aware source manifest

Each cohort can carry a frozen `CohortSourceManifest` with one binding per sample. A
binding records the opaque sample identifier, source kind and identifier, exact mzML
SHA-256 and byte size, caller-declared replicate kind (`biological`, `technical`, or
`unknown`), and any available acquisition/aliquot, PDC study/file/locator, catalog
response, receipt, or metadata-snapshot digests. The full manifest is canonicalized and
bound into the cohort configuration, result digest, and replay evidence; changing a file,
catalog response, source identity, or replicate declaration therefore cannot replay as the
same cohort.

Two biological samples may not claim the same source identity. Technical duplicate files
are retained in the matrix and remain auditable, but count neither toward independent
replicate gates nor within-label normalization support. Unknown independence is safe data
for audit but abstains from support-dependent normalization and claims. When no manifest
is supplied, the research lane creates explicit `unknown` bindings rather than inferring
independence from sample names. This is a provenance and QC boundary, not a biological
replicate classifier.

The cohort request also accepts an explicit `normalization_policy`. `none` preserves the
raw matrix and records identity scale receipts. The opt-in `within_label_median_v1` policy
uses only positive protein-group values shared by every replicate in each caller-declared
label: each sample is scaled to the median of its label's sample medians. Raw and normalized
matrices are both retained, nulls remain null, and every scale factor records its overlap,
positive-feature count, and status. A label with fewer than two replicates, no shared positive
group, or a non-finite scale abstains with an explicit status rather than imputing or emitting
a normalized value. Label QC and label-by-group evidence report descriptive median/MAD,
replicate counts, missingness, and `descriptive`/`abstained_*` statuses. Labels are caller
metadata only; this is not a case/control test, batch correction claim, differential model,
or biological interpretation.

Every cohort request also carries a closed `CohortQcPolicy` receipt. Its minimum replicate
count, minimum observed-group count, and maximum missingness rate are validated as finite
caller-declared values and included in the configuration/result digest. A label that fails an
active gate keeps its raw values for audit but receives an all-null normalized projection and an
explicit `abstained_insufficient_replicates`, `abstained_insufficient_observed_groups`, or
`abstained_missingness` status. This prevents partial observations from being presented as
normalized cohort evidence; it does not estimate missing values or promote caller labels into
biological strata.

This is evidence aggregation, not a differential-expression or cohort inference model:
there are no p-values, effect-size claims, batch correction, survival endpoints, glioma
subtype claims, mechanism discovery, or clinical recommendations. A future governed
cohort ABI still needs owner-approved cohort provenance, replicate/QC thresholds,
normalization units, missingness policy, privacy/consent boundaries, and independent
validation data.

Each `ResearchCohortResult` now carries a replay-bound `evidence_bundle` with three
content-addressed records: `cohort.matrix.v1` for raw/normalized/null-preserving values,
`cohort.qc.v1` for sample/group/label QC and replicate statuses, and
`cohort.provenance.v1` for the complete source manifest and cohort configuration. The
outer bundle digest covers the ordered record identities and each inner digest covers its
frozen payload. `aggregate_cohort_evidence` recomputes all three records without rerunning
the raw-byte computation and rejects a stale or tampered receipt. External metadata
snapshot digests must be identical across a cohort or all be absent; a mixed metadata
version is rejected rather than silently combining catalog contexts. The receipt remains
descriptive research evidence and does not authenticate issuer truth or promote caller
labels into biology.

The result carries replay-bound `PsmCompetition`, `FdrSummary`, and
`ProteinGroupFdrSummary` records. `PsmCompetition` binds the complete candidate-level
search receipt for each spectrum: target/decoy/collision candidate counts, winner and
runner-up score, score margin, and a canonical digest over each candidate's peptide,
accessions, score, matched-ion, and mass-error fields. A changed lower-scoring candidate
therefore changes the result/evidence digest even when the selected winner remains the same.
The
latter binds candidate/target/decoy/collision counts, the max-PSM-score group method,
group threshold, accepted target groups, descriptive decoy/target ratio, input versus unique
spectra, duplicate-contender count, a digest of every group contender, and shared-only/ambiguous
group counts. Accession-derived target/decoy labels are checked against each PSM's declared flags
before group scoring.
Quantification is downstream of both accepted peptide PSMs and accepted target groups;
a peptide that passes spectrum-level FDR but belongs only to a rejected or abstained
group cannot create a reported group intensity. The spectrum-level summary records
winner count per spectrum, target and decoy winner counts, accepted target count, the
declared threshold, maximum accepted q-value, and descriptive decoy/target ratio. These
are audit trails for the implemented competition rules, not claims of calibrated error
control beyond the supplied target/decoy search space.

Each PSM also records mean absolute fragment error and precursor ppm error when precursor
filtering is enabled; aggregate search diagnostics retain the maximum observed errors and
the declared precursor tolerance so a replay can audit mass-error behavior directly.

The locked evaluator covers eight paths: a target match, decoy rejection, target/decoy
sequence collision, no-match safe path, precursor rejection, shared-peptide grouping,
a two-spectrum input, and a two-peptide quantification run. Unit coverage additionally
exercises decoy-only groups, target/decoy group competition, permutation stability, and
collision abstention. The fixture binds scenario order, expected PSM/accepted counts,
target/decoy/collision winner counts, peptide and protein-group quantitative
statuses/intensities, group membership, group-FDR summaries/candidate acceptance,
shared-peptide expectations, exact FASTA/mzML SHA-256 inputs, expected result digests,
PSM peptide/q-value projections, and mass-error diagnostics. The benchmark uses one
warm-up followed by timed public calls. The package-replay CI job runs the same verifier
against the exact wheel and sdist it built, from a clean runtime whose
`glio_proteogen.research` import must resolve from that exact wheel. The wheel and sdist
are bound to their receipts; a source-tree replay or metadata-only receipt cannot mask an
artifact mismatch.

## Scientific limits

This is a transparent research computation, not a calibrated clinical estimator. It does
not perform modification-localized search, retention-time modeling, isotope/charge-state
deconvolution, DIA fragment grouping, precursor-based abundance estimation, protein
probability calibration, tissue/cell deconvolution, glioma classification, mechanism
discovery, treatment recommendation, identity inference, or consent inference. A PSM score,
q-value, spectral count, or protein group is not itself a disease or mechanistic claim.

The public PDC record used by the surrounding foundation is metadata and provenance only;
raw cohort bytes remain caller-supplied and are not bundled or downloaded implicitly. When
the caller explicitly invokes `PdcClient.download_file_with_receipt`, the retriever requires an
allowlisted HTTPS delivery host (or a caller-approved exact host), validates redirects, timeout,
response media, declared size, MD5, and SHA-256, and writes only fully verified bytes. The caller
can then supply that downloaded mzML together with a matching PDC file declaration and
content-addressed `SourceReference`, `bind_pdc_mzml_source` verifies format, locator, size,
MD5, and SHA-256 before the pipeline parses it and records the external source in evidence.
A future governed computation ABI must freeze reference/search versions, modifications and
units, FDR calibration, missingness, ambiguity, privacy/consent, validation cohorts, review,
  and safe-abstention semantics before this lane can be promoted.

### Quantification receipt and units

`QuantificationReceipt` is the explicit measurement contract for the research computation.
Its `median_scaled_matched_ion_intensity` unit is an arbitrary matched-fragment-ion signal,
not a precursor intensity, molar quantity, concentration, or cross-instrument calibrated
abundance. Repeated PSM observations for a peptide are summed once into its raw peptide
signal, and the receipt records how many input observations were collapsed. Zero signal is
represented as missing and is never converted into a positive value. The sample-median
normalization target is retained alongside raw and normalized peptide projections so a
replay can distinguish source signal from scaling. Protein-group primary intensity remains
the median of positive unique-peptide values; shared signal is visible but cannot create a
resolved group estimate.

The receipt also records descriptive signal-quality diagnostics: positive-signal fraction,
median absolute deviation (MAD), Tukey-hinge interquartile range (IQR), and MAD/median robust
CV when at least two positive peptide signals are available. A singleton is marked
`single_positive_signal`, while an empty projection is marked `no_positive_signal`; dispersion
is `null` when it is not defined. Protein-group projections carry the corresponding positive
unique-peptide count, MAD, IQR, and `unique_*` quality status. These fields expose measurement
support and heterogeneity for review and replay. They are not confidence intervals, calibrated
error bars, abundance uncertainty, or evidence of biological effect, and they never impute an
absent signal.
