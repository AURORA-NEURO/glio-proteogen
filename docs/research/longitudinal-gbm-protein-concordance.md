# Longitudinal GBM protein concordance

`kncc-gbm-longitudinal-concordance/1.0.0` is a synchronous, stateless research
model for measuring whether successive caller-supplied bulk-protein profiles
move with, against, or independently of a frozen primary-to-recurrent GBM
protein axis. It reports robust transition scores, one-sided handling of
detection limits, measurement and coefficient uncertainty, source-processing
and leave-one-driver-out ablations, their paired covariance interaction, and
exploratory change points. It does not determine tumor evolution, predict
recurrence, infer treatment response, or provide clinical advice.

The deployed estimator is repository-native. It is fitted from the public
protein matrices supporting Kim et al., *Integrated proteogenomic
characterization of glioblastoma evolution*, Cancer Cell 2024, DOI
`10.1016/j.ccell.2023.12.015`, but it is not a reproduction of every analysis in
that article. The runtime output is named source-cohort concordance rather than
patient evolution for that reason.

## Versioned source and privacy boundary

The importer accepts the three PDC000514 protein files only after checking
their exact filename, byte count, MD5, and SHA-256. Admission is also bound to
PDC study-version UUID `524d5116-b6de-4e36-892a-e35dba7d0170` through a
canonical full-response lock containing:

- the study-catalog version record;
- all 216 versioned biospecimen rows, representing 214 biological labels; and
- all 2,503 versioned file-manifest rows.

The canonical source lock is 1,362,739 bytes with SHA-256
`03d41fffeb04749296a95bd5cd5dd5829ddedc5f8f791941c011b94d6836a247`.
It is used during controlled artifact generation and is not included in the
runtime package. The source matrices and row-level biospecimen metadata also
remain outside the repository.

The importer derives exclusions from that metadata rather than a handwritten
patient list. Four incomplete patient groups contribute four excluded specimen
labels. One complete T1/T2 pair has a source-label/sample-type conflict and
contributes two more excluded labels. The resulting frozen cohort contains 104
strict pairs, with six specimen labels across five patient groups excluded.

The packaged artifact contains coefficients, aggregate support statistics,
source locks, and fit evidence only. It contains no raw patient matrix, sample
UUID, patient pseudonym, literal specimen label, or row-level label hash. Its
privacy test enumerates the complete expected `KNCC_GBM0000` through
`KNCC_GBM9999` label space, T1/T2 forms, and MD5, SHA-1, SHA-256, and SHA-512
representations. Only the bound study UUID and three source-file UUIDs are
allowed in the artifact.

The final artifact is 5,328,605 bytes. Its byte digest is
`sha256:cc965d9e9d0f7ab3e1ec7dda151bc3d5b442bbbd8cab12ee4b0f3497e860ae40`;
its canonical content digest is
`sha256:5583ee3a1d75bcd3997d12ff2102ec19fd83e49b2ec98f4f2bd9a0b6475d92a3`.
Two complete 512-replicate builds produce byte-identical output.

## Frozen source model

Blank protein cells remain missing. A source-cohort T2-minus-T1 change exists
only when both paired values exist. Technical channels are median-collapsed
within each specimen label and time point. The primary fit uses the source
`Unshared Log` measure so shared-peptide ambiguity does not silently enter the
reference axis. Source `Mean`, `Median`, and `StdDev` rows are summaries, not
genes.

Source labels are mapped through a frozen HGNC complete set using exact,
case-sensitive approved symbols first and otherwise exactly one unambiguous
previous-symbol or alias target. Ambiguous, unresolved, and colliding mappings
abstain. The final inventory contains 11,312 admitted HGNC features; 10,002
meet the training support rule.

For each eligible feature, the importer estimates a robust paired-change
center with Huber IRLS and a MAD-derived transition scale with a support-aware
variance floor. It ranks standardized source-cohort changes, selects a sparse
128-feature axis, and normalizes the absolute coefficient sum to one. The
frozen model therefore represents a direction through protein-change space,
not a recurrence classifier.

Feature-count selection is evaluated through patient-grouped nested 8x5
cross-validation. All preprocessing, scaling, ranking, and feature selection
are refit inside each training fold. Across 104 held pairs, 104 are supported,
direction accuracy is `0.7884615384615384`, and the pooled held-pair sign margin
median is `1.4985343285324095`. The reported balanced label-swap accuracy is the
algebraic sign-mirror oracle for those same held projections; it is explicitly
not independent validation.

The 512-member coefficient ensemble is a deterministic patient multinomial
bootstrap with fixed full-cohort scale and a one-step Huber influence update.
It is used only as an approximation to coefficient uncertainty. It has
`validation_role = none`; no out-of-bag performance claim is calculated from
it. Honest performance evidence comes only from nested cross-validation.

An independently frozen ordinary-`Log` projection includes shared-peptide
evidence and is used solely as a source-processing sensitivity analysis. It
does not alter or reinterpret caller quantification. The primary/ordinary
selected-feature Jaccard value is `0.6`, and the paired source-score rank
correlation is approximately `0.9980`.

## Request evidence states

A request supplies an opaque series identifier, a digest-bound normalization
reference, a required assay-compatibility attestation, and two to sixteen
ordered time points. Each time point contains typed HGNC protein observations
and an elapsed-time offset used only to establish order. Active observations
must be members of the frozen HGNC inventory and carry a quality weight and
provenance digest.

The engine is scale-specific, not a generic protein-abundance scorer. Before
any frozen KNCC coefficient or transition scale is applied, callers must supply
all fields of `assay_compatibility`; none has a default:

- `schema_version` is
  `glio-proteogen.kncc-assay-compatibility-attestation/1.0.0`;
- `compatibility_profile_id` is
  `kncc-pdc000514-tmt11-unshared-log2-ratio/1.0.0`;
- `source_profile_content_digest` is the exact frozen PDC000514 model-content
  digest `sha256:5583ee3a1d75bcd3997d12ff2102ec19fd83e49b2ec98f4f2bd9a0b6475d92a3`;
- `assay` is `tmt11_plexed_mass_spectrometry`;
- `quantification` is `unshared_peptide_protein_abundance_ratio`;
- `value_transformation` is `log2_ratio` and `log_base` is the integer `2`;
- `invariant_across_time_points` is `true`; and
- `attested_compatible` is `true`.

The normalization reference independently declares
`caller_supplied_log2_protein_abundance_ratio` as its abundance scale and is
digest-bound across every time point. Missing attestation fields, label-free or
other assays, ordinary/shared-peptide abundance, raw intensity, linear ratios,
natural-log or log10 values, and changing reference normalizations fail closed.
The profile publishes the exact accepted attestation as
`required_assay_compatibility`; the canonical request, computational seed,
profile, result, and provenance attestation digest all bind it. This is a
compatibility assertion supplied by the caller, not an automated assay
conversion or empirical cross-platform calibration.

Evidence state is explicit:

- `observed` supplies a finite log2 abundance and positive standard error;
- `left_censored` supplies a reported log2 upper detection limit and the
  uncertainty of that limit;
- `missing` and `unsupported` carry no numerical abundance and never become
  negative observations.

Duplicate identifiers, duplicate gene symbols within a time point, malformed
digests, non-finite values, inconsistent ordering, and bounded-size violations
are rejected. A transition uses only genes active at both adjacent time
points. A pair with two censored limits is uninformative.

## Runtime transition estimator

For a source coefficient \(b_g\), paired caller evidence defines a standardized
change \(d_g\) using the frozen source transition scale. The model solves a
coefficient/reliability-weighted robust location objective for the transition
score. Observed-to-observed evidence contributes a two-sided Huber residual.
Observed-to-censored and censored-to-observed evidence contribute upper or
lower hinge-Huber constraints, with the direction reversed when the source
coefficient is negative. Censored values are never sampled as hidden
abundances below their limits.

The monotone objective is solved by deterministic bounded search with ridge,
damping-equivalent bisection resolution, finite-value guards, and profile-bound
iteration limits. It is not a weighted-average proxy. Support reports the exact
shared active gene count, coefficient coverage, effective sample size, and the
transition's percentile within source-cohort support.

Classification requires the entire nominal 90% interval:

- `source_recurrence_aligned` only when its lower bound is above `+0.25`;
- `reverse_aligned` only when its upper bound is below `-0.25`;
- `stable` only when the interval lies wholly inside `[-0.05,+0.05]`;
- otherwise `indeterminate`; and
- `not_estimable` when support or uncertainty fails.

These labels describe concordance to the frozen source axis. They are not
claims that a submitted series is recurrent, progressive, responsive, or
clinically stable.

## Uncertainty, drivers, and ablations

The runtime uses 128 deterministic bootstrap perturbations by default and
accepts 32 through 256. Runs with 32 through 63 estimable projections are
explicitly `limited`; at least 64 estimable projections are required before
uncertainty can be `supported`. Numerical streams derive from the
computation-affecting request plus the source-catalog content digest; opaque
identifiers and input order do not alter the draws. A single `(replicate, time
point, gene)` draw is reused for neighboring transitions, preserving their
shared endpoint rather than creating incompatible marginal histories.

Observed values receive symmetric normal perturbations at their reported
standard errors. Censored upper limits receive symmetric perturbations of the
reported limit and remain bounds. The selected frozen coefficient replicate is
drawn from the 512-member ensemble in the same bootstrap slot. The central 5th
and 95th percentiles form the interval and are widened to contain the point
estimate.

Each paired bootstrap slot is decomposed into its frozen-coefficient-only
projection and a measurement residual, where the residual is the combined
projection minus that coefficient projection. The receipt exposes both marginal
standard errors, their signed sample covariance, the covariance's `2*covariance`
variance contribution, the combined variance, and a decomposition residual.
All identity terms are computed from the quantized values actually serialized
in the receipt; negative covariance is retained rather than clipped. The two
marginal variance fractions use only the sum of the marginal variances, remain
descriptive, and are not calibrated probabilities.

Each transition also reports signed protein drivers with value semantics,
paired source/request provenance, an exact ordinary-`Log` source-processing
ablation, and paired leave-one-driver-out bootstrap ablations. Missing or
censored support remains typed throughout every ablation. These ablations also
require at least 64 paired projections for `supported`; 32 through 63 are
`limited`.

## Change-point analysis

With at least four time points, the engine divides each adjacent transition
score by its positive elapsed duration and reports the rate on a locked 90-day
reference scale. It segments these transition rates, never cumulative protein
levels. Consequently a constant-rate trajectory with unequal observation
intervals remains constant and does not force a boundary near an endpoint.

The exact PELT recurrence uses a heteroscedastic Huber segment cost, penalty
`3.0`, and a minimum of two transitions per segment. Empirical rate standard
errors come from the common paired-bootstrap rate paths with a numerical floor.
Before candidate pruning, the engine verifies the Huber cost's `K=0`
subadditivity condition over every admissible split. Locked tests compare the
recurrence with an independent exhaustive partition search, assert the exact
candidate-set sizes on a pruning fixture, reject any failed `K=0` proof, keep a
constant-rate unequal-duration fixture boundary-free, and recover two known
step-rate boundaries.

A boundary index `b` separates transition `b-1` from transition `b`; its
time-point receipt names `time_points[b-1]` on the left and `time_points[b]` on
the right. Returned boundaries also include cost reduction and joint-bootstrap
frequency. Fewer than 32 common paths abstain, while 32 through 63 common paths
remain `limited`. This rate segmentation is exploratory and non-prescriptive.

## Replay and interfaces

The profile binds NumPy `2.5.2`, the exact required assay attestation, all solver
constants, source and mapping digests, the normalized engine AST, the synthetic
request, and a semantic demo oracle. The current profile digest is
`sha256:7890401f0166aeba54663e6cd19c3d98ee53ca7fb339f5f2ce6c92af55a71e38`.
The locked demo request, semantic oracle, and result digests are respectively:

- `sha256:e26d429a159cc0c4ec3529b6075bd4d1a77b90cb26962484eb3097f84d509f18`;
- `sha256:3e2ed92536f3a21531ef9b53710c0bc2152d30d36ff84f787b5225ba1f709ed2`;
- `sha256:02e4a6296c366b9a090fc315be275287195794e7865ddf186b8c812658976575`.

Replay recomputes the exact request and compares the request, profile, result,
transition, PELT, and full semantic payload. Requests and results are never
persisted server-side.

HTTP operations:

- `GET /v1/research/longitudinal-gbm/profile`
- `GET /v1/research/longitudinal-gbm/demo`
- `POST /v1/research/longitudinal-gbm/analyze`
- `POST /v1/research/longitudinal-gbm/verify`

Matching CLI commands are available under `glio-proteogen longitudinal-gbm
profile|demo|analyze|verify`. Requests are capped at 2 MiB, results at 4 MiB,
and replay envelopes at 8 MiB. The adapter admits two computations per process,
runs CPU work outside the event loop, and enforces disconnect cancellation,
deadlines, strict duplicate-key JSON parsing, sanitized errors, and `no-store`
receipts. Cooperative cancellation checkpoints occur within bootstrap drawing,
robust projection, source and top-driver ablations, segment-location/cost loops,
the exact PELT dynamic program and pruning proof, and its brute-force oracle;
cancellation therefore does not wait for an entire expensive phase to finish.
The HTTP computation deadline is 120 seconds. The workbench waits 130 seconds,
leaving enough transport margin for the backend to return a typed deadline
receipt; this client margin does not widen the server limit.

The synthetic four-time-point demo uses real frozen model feature identities
with generated observations. It contains aligned, reverse-aligned, and stable
transitions. Its requested 32 bootstrap replicates intentionally make each
transition and its no-boundary rate segmentation `limited`. It contains no
patient data and is an implementation oracle, not biological validation.
