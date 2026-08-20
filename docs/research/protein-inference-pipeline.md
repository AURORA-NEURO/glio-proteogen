# Research protein-inference pipeline (non-governed)

This document describes the executable research lane added on top of the public-
proteomics foundation. It is intentionally not a GLIO-PROTEOGEN production module
and does not widen M03/M04 contracts.

## Computation performed

`run_research_protein_inference` accepts caller-owned mzML and FASTA bytes and applies
one deterministic, auditable path:

1. Decode bounded mzML spectra and retain MS2 spectra only for identification.
   The parser drains caller-supplied uncompressed binary streams to EOF within
   the byte cap, including when individual ``read(n)`` calls return short chunks;
   this keeps direct parser use replay-stable instead of silently analyzing a
   valid prefix. Gzip streams are drained through the same bounded decoder.
   A spectrum with multiple selected ions is marked as ambiguous and abstains
   from this single-precursor search rather than inheriting a document-order
   ``cvParam`` value.
   An optional caller-supplied mzIdentML file is structurally parsed separately;
   its bytes, identifiers, identification-result/item counts, peptide-evidence count,
   protein-detection-hypothesis count, and pass-threshold item count become a receipt.
   The pipeline never imports mzIdentML PSMs or protein hypotheses into its own search
   or grouping computation.
2. Drain caller-supplied FASTA byte streams to EOF within the bounded byte limit, then
   digest entries with trypsin and the declared missed-cleavage and peptide-length controls;
   short reads cannot silently truncate the searched protein space.
3. Score theoretical b/y fragments against observed m/z/intensity arrays using the
   explicit fragment tolerance and minimum matched-ion threshold. Only strictly
   positive-intensity positions count as observed fragment evidence; zero-signal
   m/z slots are ignored and an all-zero spectrum abstains. Overlapping
   tolerance windows use a deterministic maximum-cardinality, minimum-total-error
   one-to-one assignment rather than consuming peaks in theoretical-ion iteration
   order; this prevents a valid later ion from being erased by a greedy match.
4. Apply the caller-declared integer precursor tolerance (0–500 ppm) to the selected
   mzML precursor m/z and charge before fragment candidates enter competition. The
   tolerance, observed precursor error diagnostics, and missing-precursor abstentions
   are part of the run configuration and result digest; a changed tolerance therefore
   cannot replay as the same computation.
5. Retain every precursor-compatible candidate in a per-spectrum competition receipt,
   including target/decoy/collision counts, winner/runner-up scores, score margin, and a
   canonical candidate digest. The legacy single-winner projection is derived from this
   receipt; lower-scoring contenders are never silently discarded from replay evidence.
   Exact-score contenders are canonically ordered by their complete PSM projection after
   score/class/identity policy, so winner selection and contender digests are permutation-stable.
6. Perform target/decoy competition and calculate monotone q-values. A spectrum whose
   peptide maps to both target and decoy accessions is recorded as a collision and
   conservatively abstained rather than promoted to either side. Collision winners remain
   conservative decoy evidence in the descriptive FDR numerator, so an abstained collision
   cannot disappear from the error estimate. If the winner table contains no decoy or
   collision winner, there is no empirical error estimate: target q-values are `null` and
   peptide/group acceptance abstains. Both peptide- and group-FDR boundaries reject PSMs with
   zero matched fragments or ambiguous accession identity before competition; an unobserved
   decoy count is never treated as zero FDR. PSMs are accepted only at the caller-declared
   q-value threshold.
7. Resolve protein-group candidates from the scored PSMs, including target, decoy, and
   mixed target/decoy collision evidence. Duplicate contenders for one spectrum are reduced to
   one deterministic winner for scoring, while a canonical digest of every contender remains in
   the group summary. Each candidate receives a deterministic max-supporting-PSM score and
   monotone group-level target/decoy q-value. Decoy groups are rejected, mixed groups are retained
   as null-q collision abstentions. Collision groups still count in the group-FDR numerator,
   while shared-only groups and partially unique connected groups are marked ambiguous before
   quantification. Only fully uniquely supported target groups passing this second threshold
   become reportable groups.
   This is transparent group-FDR evidence, not a calibrated protein probability.
8. Aggregate matched fragment-ion intensity for peptides belonging to reportable groups
   and median-normalize within the sample with explicit zero-signal missingness; spectral
   counts remain a separate transparent measure. Every run emits a replay-bound
   quantification receipt containing the arbitrary measurement unit, raw and normalized
   peptide signals, duplicate-observation count, positive/missing counts, raw median,
   normalization target, and scale factor. The run configuration and computed protein-group
   evidence derive their quantification version and unit directly from this receipt, so
   `none_v1` is reported as arbitrary matched-ion intensity rather than median-scaled signal.
   Under `none_v1`, the receipt leaves `normalization_target` and `scale_factor` null because
   no normalization operation was applied; a raw median is not presented as an executed scale.
   The `max_input_observations` admission bound is enforced while iterating, before a
   lazy producer can be fully materialized; an oversized iterable therefore fails at
   the first excess item and cannot bypass the bounded receipt contract.
   Receipt LOQ is validated as finite and non-negative, and status counters as
   non-negative integers, including fields omitted from the compact default projection.
   Per-peptide raw and normalized status vectors are bound whenever present, even
   under the default policy, so replay cannot silently replace quantified/missing
   status evidence.
9. Quantify each reportable protein group from the median positive unique-peptide
   intensity. Shared signal remains visible, but shared-only groups are explicitly
   non-quantifiable rather than assigned a fabricated protein value.
10. Emit SHA-256 input/evidence/result digests and permit a complete deterministic replay.

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
hatch whose mixed, receipt-bound source identities remain fully recorded. Even under
`mixed_declared`, a request carrying an external PDC file declaration without a
`PdcSourceReceipt` is rejected at the cohort admission boundary; otherwise that file could
be mislabeled as a local source in the manifest. Receipt fields are retained per child and
remain bound through child result digests, so a file rename, response change, or source
substitution cannot replay as the same cohort.

When a PDC file declaration is supplied without a catalog receipt, its source-reference media
type is still checked against the declared `mzML`/`mzML.gz` format before parsing, so a text or
unrelated-media label cannot be attached to otherwise matching bytes.

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
SHA-256 and non-negative integer byte size, caller-declared replicate kind (`biological`, `technical`, or
`unknown`), and any available acquisition/aliquot, PDC study/file/locator, catalog
response, receipt, or metadata-snapshot digests. The full manifest is canonicalized and
bound into the cohort configuration, result digest, and replay evidence; changing a file,
catalog response, source identity, or replicate declaration therefore cannot replay as the
same cohort.

Two biological samples may not claim the same source identity, declared aliquot identity,
or acquisition identity when those caller-declared fields are present. Technical duplicate files
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

Technical replicates are retained in the raw matrix but are never used as independent
biological support for a label's normalization center or replicate gate. When a label contains
both biological and technical rows, `within_label_median_v1` computes scale factors only for
the biological rows; each technical row receives `scale_factor=null`, the explicit
`abstained_technical_replicate` row status, and an all-null normalized row. Its raw values,
source binding, and QC evidence remain visible, while `independent_observed_replicates` and
label medians count biological rows only. This is deliberate non-imputation and safe
abstention, not a claim that the technical measurement is biologically negative or unusable.

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

Each `ResearchCohortResult` now carries a replay-bound `evidence_bundle` with four
content-addressed records: `cohort.matrix.v1` for raw/normalized/null-preserving values,
`cohort.qc.v1` for sample/group/label QC and replicate statuses,
`cohort.provenance.v1` for the complete source manifest and cohort configuration, and
`cohort.contrast.v1` for pairwise descriptive label contrasts. A contrast is computed only
from positive normalized label medians and records median difference, ratio, log2 ratio,
observed replicate counts, missingness, and the source label QC statuses. Missing or
non-positive cells produce `abstained_missing_or_nonpositive` with no imputation. Labels
are compared in canonical lexical order as caller metadata; they are never interpreted as
case/control, disease, treatment, or biological strata, and no p-value or significance
claim is emitted. The contrast constructor verifies that difference, ratio, and log2 ratio
are derived from the recorded medians, so a direct receipt cannot overstate the descriptive
effect while retaining a valid outer digest. The outer bundle digest covers the ordered record identities and each
inner digest covers the complete record identity (`evidence_id`, `source`, and `kind`) as
well as its frozen payload and quality metadata. Relabeling a record while retaining its
old digest therefore fails replay; an evidence ID is not an interchangeable display label.
`aggregate_cohort_evidence` recomputes all four records without rerunning the raw-byte
computation, re-derives normalized matrices, sample scales, label QC, label-by-group evidence,
matrix-derived group/sample QC, and label contrasts from their upstream projections, verifies the
complete outer result digest, and rejects a stale, tampered, or internally inconsistent receipt.
Positive medians from labels whose QC
status is not exactly `descriptive` are also withheld: they produce `abstained_label_qc` with
null difference, ratio, and log2-ratio fields. This prevents unknown-independence, missingness,
or insufficient-support labels from being presented as derived effects while retaining their
raw and QC evidence.
External metadata
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
The public receipt constructor validates accession-derived target/decoy/collision class and
finite measurement fields before counting candidates; callers using a custom decoy namespace
must pass that exact prefix. This prevents a forged decoy flag from becoming target evidence
when the receipt is built outside the full pipeline.
The bounded pilot forwards `SearchParameters.decoy_prefix` into both winner-level FDR
and downstream protein-group classification, so a custom decoy namespace cannot silently
fall back to `DECOY_` during the final scoring pass.
The
latter binds candidate/target/decoy/collision counts, the max-PSM-score group method,
group threshold, accepted target groups, descriptive decoy/target ratio, input versus unique
spectra, duplicate-contender count, a digest of every group contender, and shared-only/ambiguous
group counts. Accession-derived target/decoy labels are checked against each PSM's declared flags
before group scoring. Both peptide- and group-level descriptive decoy/target ratios count
collision evidence conservatively, even though collision records remain non-reportable. Target-
only group candidates retain their evidence but have `null` q-values and cannot become accepted
groups without decoy/collision error evidence.
When the target denominator is zero (decoy-only or collision-only evidence), the descriptive
decoy/target ratio is `null` rather than `0.0`: the error rate is undefined, not zero. A numeric
zero is reserved for a positive target denominator with no decoy or collision winners.
Quantification is downstream of both accepted peptide PSMs and accepted target groups;
a peptide that passes spectrum-level FDR but belongs only to a rejected or abstained
group cannot create a reported group intensity. The spectrum-level summary records
winner count per spectrum, target and decoy winner counts, accepted target count, the
declared threshold, maximum accepted q-value, and descriptive decoy/target ratio. These
are audit trails for the implemented competition rules, not claims of calibrated error
control beyond the supplied target/decoy search space.

Each PSM also records mean absolute fragment error and precursor ppm error when precursor
filtering is enabled; aggregate search diagnostics retain the maximum observed errors and
the caller-declared precursor tolerance so a replay can audit mass-error behavior directly.
The locked precursor-policy evaluator includes a deliberately near-boundary precursor
fixture: the 1 ppm policy abstains at approximately 1.07 ppm error, while the 20 ppm
policy accepts, and replay with the changed policy is rejected. This validates a scientific
threshold and its digest boundary rather than only checking that a field serializes.

### Optional mzIdentML provenance

`ResearchRunRequest.mzidentml_source` is an explicit, bounded structural-evidence input.
The parser rejects malformed/unsafe XML and records an exact SHA-256, identifier digest,
result/item/evidence/hypothesis counts, and pass-threshold item count in the run
configuration, evidence bundle, result projection, and replay digest. Providing or
changing this file therefore changes the content-addressed run even when mzML/FASTA
search output is unchanged. This is provenance of an external identification artifact,
not acceptance of its PSMs, protein hypotheses, FDR, or biological claims.

Every single-run result also carries the complete `EvidenceBundle` projection, including
each record's identity, payload, quality metadata, the derived quality summary, limitations,
and outer digest. `verify_evidence_bundle` recomputes each identity-and-payload-bound inner
digest, the ordered outer digest, and all derived quality fields before replay. This keeps a
forged source/kind/evidence-ID relabeling or completeness/auditability summary from remaining
invisible merely because the underlying raw records are unchanged.
Evidence payloads reject non-finite floating-point values before hashing, so NaN or infinite
measurements cannot enter a permissive JSON digest and masquerade as replayable evidence.

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
raw cohort bytes remain caller-supplied and are not bundled or downloaded implicitly. The
bounded metadata transport drains short reads to EOF before hashing the response, so a legal
partial network read cannot produce a self-consistent receipt for only a valid JSON prefix.
When
the caller explicitly invokes `PdcClient.download_file_with_receipt`, the retriever requires an
allowlisted HTTPS delivery host (or a caller-approved exact host), validates redirects, timeout,
response media, declared size, MD5, and SHA-256, and writes only fully verified bytes. The caller
can then supply that downloaded mzML together with a matching PDC file declaration and
content-addressed `SourceReference`, `bind_pdc_mzml_source` verifies format, locator, size,
MD5, and SHA-256 before the pipeline parses it and records the external source in evidence.
The resulting PDC receipt also preserves the normalized response `Content-Type`, bound to the
catalog format and source-reference media, so transport relabeling changes the receipt digest
and is rejected. This records delivery provenance only; it does not establish issuer truth or
biological validity.
When bytes are obtained through another approved path, `verify_pdc_source_content` recomputes
the receipt's SHA-256, catalog MD5, and exact byte length over caller-held bytes or a bounded
  binary stream. The stream is drained to EOF even when individual `read(n)` calls short-read;
  over-length content is rejected before acceptance, and no raw bytes are persisted by the
  verifier. This prevents a throttled or non-seekable stream from silently contributing only a
  prefix and closes the gap between a serialized
caller-supplied receipt and the content actually used for parsing.
A future governed computation ABI must freeze reference/search versions, modifications and
units, FDR calibration, missingness, ambiguity, privacy/consent, validation cohorts, review,
  and safe-abstention semantics before this lane can be promoted.

### Fragment charge search space

The research search now supports an explicit tuple of fragment-ion charge states. The
original one-plus-only primitive remains available through `SearchParameters`' default
`fragment_charges=(1,)`; the mzML pipeline declares `(1, 2)` so doubly charged b/y ions are
eligible when their observed m/z values support them. Each charged ion is derived from the
same modification-aware singly charged mass, and one-to-one peak assignment still prevents
one observed peak from counting for multiple ions. The tuple is validated, serialized into
the run configuration, and therefore bound to replay/result digests. This is a search-space
extension, not charge-state deconvolution or abundance inference: unobserved/ambiguous
precursor metadata still abstains and the output remains research-only.

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

`QuantificationPolicy` makes the remaining controls explicit and replay-bound. Only arbitrary
matched-ion intensity is accepted; normalization is either `none_v1` or
`sample_median_scaled_v1`; and a finite caller-declared limit of quantification (LOQ) may be
applied. A zero or below-LOQ raw signal remains visible in the raw receipt but is projected as
missing with zero normalized signal and no imputation. The policy, below-LOQ count, and per-
peptide status vectors are included in the non-default configuration/receipt digest, so a
replay cannot silently change units, normalization, or LOQ semantics. The LOQ is not an
empirical assay calibration and does not establish clinical detectability.

All search and matched-ion numeric boundaries reject booleans explicitly. Although Python
`bool` is an `int` subclass and `math.isfinite(True)` is true, a metadata flag is not a valid
m/z, precursor, intensity, or PSM score. Such values are rejected before arithmetic; missing or
unsupported measurements abstain rather than being coerced into one-unit signal.
