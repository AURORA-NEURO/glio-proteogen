# Scientific computation foundation (research-only)

This lane is an additive research foundation, not a replacement for any frozen GLIO-PROTEOGEN
module ABI. It exists because the current M03/M04 contracts deliberately stop at bounded raw-byte
admission, metadata quality, artifact evidence, harmonization, and support routing. Those modules
must not be silently widened to claim protein, proteoform, isoform, abundance, glioma, or mechanism
inference.

The foundation provides real computational primitives that can be wired into a future owner-approved
C03/C04 computation contract:

- `PdcClient` retrieves bounded public NCI Proteomic Data Commons metadata over the documented open
  GraphQL endpoint. It records the study URL, file metadata, and response SHA-256; its explicit
  `download_file_with_receipt` path additionally binds one caller-requested download to the exact
  captured catalog file and observed SHA-256/MD5/size. The opt-in raw-byte path requires an HTTPS
  PDC delivery host or an exact caller-approved host (loopback HTTP is test-only), bounds timeout
  and decoded bytes, validates mzML media and declared length, revalidates every redirect, and
  stages bytes until all catalog/reference hashes pass. It never fetches raw cohort data implicitly.
- `parse_mzml` decodes bounded m/z and intensity arrays from local mzML or gzip-compressed mzML.
- `read_fasta` and `digest_trypsin` build an explicit search-space peptide index.
  `build_search_space` can additionally construct one deterministic reversed-protein
  decoy per target entry, or retain caller-declared decoys, and emits a content-addressed
  `SearchSpaceReceipt` recording target/decoy entries, peptide counts, collision peptides,
  digestion controls, and the complete peptide map. The strategy is explicit rather than
  silently assuming that a decoy database exists; reversed decoys are a research control,
  not a universally calibrated error model.
- `search_spectrum` scores theoretical b/y fragments against observed peaks. It is an auditable
  matching score, not a calibrated probability.
- `search_spectrum_candidates` retains every compatible candidate for one spectrum and
  `PsmCompetition` binds target/decoy/collision counts, score margin, and a canonical digest
  over candidate scoring inputs. The pipeline derives its winner/q-value projection from this
  receipt, so a changed lower-scoring contender cannot silently replay as the same result.
- `target_decoy_qvalues` performs explicit target/decoy competition and preserves
  target/decoy sequence collisions as conservative abstentions.
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
- `infer_protein_groups` applies deterministic parsimony and retains shared-peptide ambiguity
  instead of collapsing indistinguishable proteins.
- `infer_protein_group_candidates` deterministically reduces duplicate spectrum contenders before
  group scoring, validates that target/decoy flags agree with accession labels, and binds a
  canonical digest of every contender. It retains target/decoy/collision evidence, computes
  monotone max-PSM-score group q-values, rejects decoy groups, abstains on mixed collisions, and
  exposes unique-peptide versus shared-only identifiability before quantification. The summary
  records input-versus-unique spectra and shared-peptide counts, so a changed lower-scoring
  contender cannot replay as the same group result. This is transparent research FDR evidence,
  not a calibrated protein probability.
- `aggregate_evidence` creates a stable content-addressed evidence bundle with explicit limits.
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
  or metadata snapshot digests, while retaining a declared biological/technical/unknown
  replicate kind. Biological reuse of one source is rejected; technical reuse remains visible
  but cannot inflate independent-replicate or normalization support; unknown independence
  abstains support-dependent projections. No independence is inferred from names or order.
- Every cohort result also carries three inner evidence receipts (`cohort.matrix.v1`,
  `cohort.qc.v1`, and `cohort.provenance.v1`) inside one content-addressed bundle. The
  public `aggregate_cohort_evidence` helper recomputes and verifies these receipts without
  re-reading raw spectra, so a changed matrix, QC decision, source manifest, or metadata
  snapshot cannot be presented with an old cohort evidence digest. Metadata snapshot
  versions must be uniform within one cohort or the run rejects before emitting an
  aggregate.

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
