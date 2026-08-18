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
4. Perform target/decoy competition and calculate monotone q-values. PSMs are accepted
   only at the caller-declared q-value threshold.
5. Quantify accepted peptides by spectral counts, preserving zero observations rather
   than converting missingness to a negative measurement.
6. Resolve protein groups with the existing ambiguity-preserving parsimony routine;
   shared peptides remain attached to all compatible accessions.
7. Emit SHA-256 input/evidence/result digests and permit a complete deterministic replay.

The locked evaluator covers six paths: a target match, decoy rejection, no-match safe path,
precursor rejection, shared-peptide grouping, and a two-spectrum input. The fixture binds
scenario order, expected PSM/accepted counts, group membership, shared-peptide expectations,
and all claim-boundary flags. The benchmark uses one warm-up followed by timed public calls.

## Scientific limits

This is a transparent research computation, not a calibrated clinical estimator. It does
not perform modification-localized search, retention-time modeling, isotope/charge-state
deconvolution, DIA fragment grouping, intensity-based abundance estimation, protein
probability calibration, tissue/cell deconvolution, glioma classification, mechanism
discovery, treatment recommendation, identity inference, or consent inference. A PSM score,
q-value, spectral count, or protein group is not itself a disease or mechanistic claim.

The public PDC record used by the surrounding foundation is metadata and provenance only;
raw cohort bytes remain caller-supplied and are not bundled or downloaded implicitly. A
future governed computation ABI must freeze reference/search versions, modifications and
units, FDR calibration, missingness, ambiguity, privacy/consent, validation cohorts, review,
and safe-abstention semantics before this lane can be promoted.
