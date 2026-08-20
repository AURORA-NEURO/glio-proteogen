# Scientific computation foundation (research-only)

This lane is an additive research foundation, not a replacement for any frozen GLIO-PROTEOGEN
module ABI. It exists because the current M03/M04 contracts deliberately stop at bounded raw-byte
admission, metadata quality, artifact evidence, harmonization, and support routing. Those modules
must not be silently widened to claim protein, proteoform, isoform, abundance, glioma, or mechanism
inference.

The foundation provides real computational primitives that can be wired into a future owner-approved
C03/C04 computation contract:

- `PdcClient` retrieves bounded public NCI Proteomic Data Commons metadata over the documented open
  GraphQL endpoint and rejects returned study metadata or files whose study identity differs from
  the requested catalog study. Each metadata snapshot also binds its query digest, response hash,
  response size, endpoint, and source identity before it can enter downstream evidence. It records
  the study URL, file metadata, and response SHA-256; its explicit
  `download_file_with_receipt` path additionally binds one caller-requested download to the exact
  captured catalog file and observed SHA-256/MD5/size. The opt-in raw-byte path requires an HTTPS
  PDC delivery host or an exact caller-approved host (loopback HTTP is test-only), bounds timeout
  and decoded bytes, validates mzML media and declared length, revalidates every redirect, and
  stages bytes until all catalog/reference hashes pass. It never fetches raw cohort data implicitly.
  The resulting `PdcSourceReceipt` also records the normalized response media type and binds it
  to the catalog format and caller source-reference media, so a replay cannot relabel verified
  mzML bytes as another transport format. This is provenance evidence, not issuer or biological
  validity evidence.
- `parse_mzml` decodes bounded m/z and intensity arrays from local mzML or gzip-compressed mzML.
- `read_fasta` and `digest_trypsin` build an explicit search-space peptide index.
- The run pipeline accepts an optional bounded mzIdentML byte stream only as structural
  provenance: safe XML parsing records its exact SHA-256, identifier digest, result/item,
  peptide-evidence, protein-detection-hypothesis, and pass-threshold counts. Those
  fields are replay-bound and can be changed without changing the independently computed
  mzML/FASTA PSM projection; mzIdentML PSMs and hypotheses are never imported into
  search or protein grouping.
- `search_spectrum` scores theoretical b/y fragments against observed peaks. Overlapping
  fragment-tolerance windows are resolved by a deterministic maximum-cardinality, minimum-error
  one-to-one assignment, with stable m/z/index ordering for exact ties; this avoids greedy peak
  consumption changing matched-ion counts. Direct candidate search rejects non-finite or
  non-positive observed m/z values, so a broad tolerance cannot turn placeholder zero peaks into
  fragment evidence. The assignment algorithm version is bound into the composed pipeline
  configuration and replay digest. It is an auditable matching score, not a calibrated probability.
- `parse_modified_peptide` and `expand_peptide_map` provide a bounded residue-local catalogue
  (`UNIMOD:4`, `UNIMOD:21`, and `UNIMOD:35`). Declared modification deltas participate in both
  precursor and fragment masses; unknown, undeclared, terminal, and residue-incompatible forms
  abstain. Variable-modification rules, site limits, target/decoy variant counts, modified
  target/decoy overlap, and unique variant-space size are bound in
  the search-space receipt and run configuration. This is a constrained research surface, not a
  full ProForma implementation or a production PTM/localization claim. Target/decoy pair
  compatibility is based on unmodified cleavage products; PTM eligibility cannot masquerade as
  a digestion mismatch in the FDR search-space receipt.
- `search_spectrum_candidates` retains every compatible candidate for one spectrum and
  `PsmCompetition` binds target/decoy/collision counts, score margin, and a canonical digest
  over candidate scoring inputs. The pipeline derives its winner/q-value projection from this
  receipt, so a changed lower-scoring contender cannot silently replay as the same result.
  Building a competition receipt directly also validates accession-derived class flags and
  finite measurement fields; custom decoy prefixes must be supplied explicitly at that boundary.
- `target_decoy_qvalues` performs explicit target/decoy competition and preserves
  target/decoy sequence collisions as conservative abstentions. Equal-score collision and
  decoy winners are ordered before targets even across different spectra, so lexical spectrum
  IDs cannot manufacture a zero q-value. Collision winners remain
  in the descriptive FDR numerator rather than being silently removed from error evidence.
  A winner table with no decoy or collision evidence has no empirical error estimate:
  target q-values are then null and the pipeline/group projection abstains from reporting
  targets while retaining the candidate and its descriptive receipt. It never treats an
  unobserved decoy count as a zero FDR estimate.
- The composed pipeline requires a selected-ion precursor m/z and charge for MS2
  matching and applies a caller-declared integer precursor tolerance bounded to
  0–500 ppm. The tolerance is applied before candidate competition and is bound into
  diagnostics, configuration, result digest, and replay; missing precursor metadata
  or multiple selected ions abstain rather than opening an implicit open search or
  inheriting an arbitrary last precursor. This is an auditable mass filter, not a
  calibrated identification probability.
- `summarize_target_decoy` records winner-level target/decoy counts, accepted targets, threshold,
  and descriptive decoy/target ratio in the replay-bound result evidence.
- `quantify_matched_ions` aggregates finite matched-fragment intensity per peptide and applies
  median scaling while preserving zero-signal missingness. `quantify_protein_groups` reports
  unique/shared/total signal and uses only positive unique-peptide medians for a primary group
  intensity; shared-only groups remain explicitly non-quantifiable. Neither is precursor-based
  abundance.
- `quantify_matched_ions_with_receipt` additionally returns a replay-bound
  `QuantificationReceipt`: arbitrary matched-ion units, raw/normalized peptide signals,
  duplicate-observation collapse, positive/missing counts, raw median, normalization target,
  scale factor, positive-signal fraction, and descriptive MAD/IQR/robust-CV quality diagnostics
  are all explicit. Single-positive and no-positive projections are labeled rather than given
  fabricated dispersion. This prevents a normalized research signal from being mistaken for
  calibrated abundance while retaining enough computation detail to audit support and
  heterogeneity.
- The research-only `QuantificationPolicy` closes the remaining scale ambiguity. It permits
  only arbitrary matched-ion intensity, explicitly selects either no normalization or
  sample-median scaling, accepts a finite caller-declared limit of quantification (LOQ), and
  bounds the materialized observation count. The receipt carries an order-invariant digest of
  the complete peptide/intensity multiset plus the active observation ceiling.
  A zero or below-LOQ signal is retained in the raw receipt but becomes a null-equivalent
  missing projection with no imputation. Non-default policy fields, below-LOQ counts, and
  per-peptide status vectors are part of the single-run configuration/receipt digest, so a
  replay cannot silently change units, normalization, LOQ semantics, or the input observations.
  The composed pipeline copies the receipt's algorithm version and measurement unit into both
  run configuration and computed protein-group evidence; a `none_v1` run therefore reports
  arbitrary matched-ion intensity rather than the median-scaled unit. Its receipt also leaves
  the normalization target and scale factor null because no normalization operation was applied.
- Protein-group quantification now validates the input partition before computing any
  signal: accessions and peptide memberships must be disjoint across groups, and every
  supplied intensity or PSM-count key must belong to that declared partition. Each
  emitted group carries a deterministic `protein-group-quantification-input-1` digest
  over its group membership plus present-versus-missing intensity/count observations.
  This prevents shared peptides from being double-counted and prevents unreferenced
  evidence from disappearing silently. It remains matched-ion research signal, not
  protein abundance, protein identity, proteoform inference, or clinical evidence.
- `infer_protein_groups` applies deterministic parsimony and retains shared-peptide ambiguity
  instead of collapsing indistinguishable proteins.
- `infer_protein_group_candidates` deterministically reduces duplicate spectrum contenders before
  group scoring, validates that target/decoy flags agree with accession labels, and binds a
  canonical digest of every contender. It retains target/decoy/collision evidence, computes
  monotone max-PSM-score group q-values, rejects decoy groups, abstains on mixed collisions, and
  counts collision groups conservatively in the group-FDR numerator while keeping them
  non-reportable,
  exposes unique-peptide versus shared-only identifiability before quantification. The summary
  records input-versus-unique spectra and shared-peptide counts, so a changed lower-scoring
  contender cannot replay as the same group result. A target group supported only by shared
  peptides remains visible with shared signal and an explicit `abstained` acceptance; a connected
  group in which only some accessions have unique-peptide support is also marked
  `partially_unique_ambiguous` and abstained. Neither can become a reportable primary estimate
  merely because its group q-value is numerically small.
  Direct target/decoy q-value entry also validates accession-derived class flags before
  competition, preventing a forged decoy from entering the target denominator. This is
  transparent research FDR evidence, not a calibrated protein probability.
- `aggregate_evidence` creates a stable content-addressed evidence bundle with explicit limits.
  Canonical payloads reject non-string mapping keys instead of coercing them, preventing key
  collisions and silent evidence loss before record digests are computed.
  Each record may additionally carry an `EvidenceQuality` assessment that separates
  byte/computation auditability, observed completeness, and caller-declared independent source
  count. `EvidenceQualitySummary` reports a deterministic source-count-weighted auditability
  projection and is explicitly not a probability of biological truth. Aggregation rejects two
  different payloads claiming the same source/kind so a stale or contradictory external receipt
  cannot silently coexist with a newer one under a different evidence ID.
- `aggregate_external_evidence` provides a separate external-cohort evidence ledger. Each
  observation is bound to an opaque caller claim, study/source identity, source SHA-256/size, and
  method ID. The ledger preserves caller-declared support, contradiction, inconclusive, and
  abstained directions; repeated observations from one source are not counted as independent, and
  contradictory directions from one source force an explicit abstention. The aggregate emits only
  descriptive status/counts and a replay-bound `EvidenceBundle`: it performs no numerical fusion,
  p-value calculation, posterior inference, disease labeling, or mechanism discovery. An
  independent-source threshold is an auditability gate, not statistical power or biological truth.
- `run_research_protein_inference` composes those primitives into an executable mzML-to-FASTA
  research run: fragment matching, target/decoy q-values, spectral counts, matched-ion
  intensity quantification, ambiguity-preserving protein groups, and deterministic replay.
- `run_research_cohort` composes compatible child runs into a deterministic sample-by-group
  matrix with explicit null missingness, replicate QC (median/MAD), child/source digests, and
  replay verification. Its opt-in `within_label_median_v1` normalization computes bounded
  scale factors only from positive groups shared by every replicate of a caller-declared label,
  retaining raw and normalized matrices plus label/group descriptive evidence. Insufficient
  overlap or replicate support abstains explicitly; no null is imputed. It aggregates evidence
  only; it does not perform differential testing, batch correction, glioma inference, or
  mechanism discovery.
- Cohort QC is an explicit, replay-bound `CohortQcPolicy`: minimum replicates, minimum observed
  groups, and maximum missingness are validated before normalized evidence is emitted. Failed
  gates preserve the raw matrix for audit but null the normalized label projection and emit a
  typed abstention status; the policy never imputes values or infers biological strata.
- Cohort source identity is a separate replay-bound `CohortSourceManifest`. It binds each
  sample to the exact source digest/size and any caller-provided PDC file, catalog, receipt,
  or PDC metadata snapshot digests, while retaining a declared biological/technical/unknown
  replicate kind. Biological reuse of one source, declared aliquot, or acquisition identity is
  rejected; technical reuse remains visible but cannot inflate independent-replicate or
  normalization support; unknown independence abstains support-dependent projections. No
  independence is inferred from names or order.
- Every cohort result also carries three inner evidence receipts (`cohort.matrix.v1`,
  `cohort.qc.v1`, and `cohort.provenance.v1`) inside one content-addressed bundle. The
  public `aggregate_cohort_evidence` helper recomputes and verifies these receipts without
  re-reading raw spectra, re-derives normalized matrices, sample scales, label QC,
  label-by-group evidence, matrix-derived group/sample QC, and label contrasts, and rejects
  internally inconsistent projections as well as stale or tampered receipts. A changed matrix,
  QC decision, source manifest, or metadata snapshot cannot be presented with an old cohort
  evidence digest. Each inner digest binds the record's `evidence_id`, `source`, and `kind` in
  addition to its payload and quality;
  relabeling provenance while preserving the old digest is rejected. Metadata snapshot
  versions must be uniform within one cohort or the run rejects before emitting an
  aggregate.
  Their quality assessments distinguish complete versus missing matrix support and bind the
  number of distinct source identities without treating technical replicates as independent
  biological evidence. Quality scores remain auditability/completeness metadata, not confidence
  in a protein, disease, or mechanism claim.

- `verify_pdc_source_content` recomputes the catalog-bound SHA-256, MD5, and exact byte length
  over caller-held raw bytes or a bounded one-pass stream. It turns a serialized PDC receipt
  into a content check without persisting or interpreting the raw file; mismatched, truncated,
  and over-limit content is rejected before a caller can parse it.

The checked-in external record is public PDC000204 metadata for the CPTAC GBM Discovery Study. It
contains file counts and one representative processed-mzML file declaration, not patient records or
redistributed raw spectra. The representative file is 193,963,708 bytes and is fetched only by an
explicit caller action. Public cohort evidence is catalog-attested when a `PdcSourceReceipt` is
present; the receipt proves byte/catalog identity but not issuer truth, consent, or clinical validity.

## Production boundary

This package is intentionally not imported by M03/M04 execution routes and emits no clinical,
disease, treatment, glioma-specific, proteoform, or mechanistic claim. A production module still
needs owner confirmation of:

1. licensed/public fixture provenance and consent/DUA boundaries;
2. search-space/reference versions, digestion/modification rules, precursor/fragment tolerances;
3. PSM scoring, target/decoy FDR, quantification units and normalization policy;
4. shared-peptide/protein-group ambiguity and missingness semantics;
5. result privacy, review, uncertainty, replay, and safe-abstention contracts.

The research implementation is deliberately useful before that handoff without pretending that a
caller-declared proxy is a scientific result.

The composed workflow and its exact limitations are recorded in
`docs/research/protein-inference-pipeline.md`. It remains research-only and is not imported by
M03/M04 routes.
