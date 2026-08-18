# Research foundation evidence

The research-only foundation is covered by `tests/research/test_scientific_foundation.py`.

Evidence includes:

- a captured public PDC GraphQL response shape for PDC000204 (CPTAC GBM Discovery Study);
- bounded mzML binary-array decoding;
- tryptic digestion and explicit FASTA search-space construction;
- fragment matching, target/decoy q-value calculation, and shared-peptide protein grouping;
- deterministic group-level target/decoy FDR with duplicate-spectrum contender reduction,
  accession/flag consistency checks, contender digests, and explicit shared-only ambiguity;
- deterministic peptide-intensity median normalization with missingness preservation;
- order-stable content-addressed aggregation of external-cohort and computed evidence.
- exact PDC receipt binding for cohort manifests: source ID, catalog-response digest, file name,
  locator, study, and receipt digest must all match the embedded receipt; forged identity fields
  are rejected before cohort aggregation.

The PDC record is metadata provenance, not a claim about patient-level biology. The foundation is
not a production GLIO-PROTEOGEN module and does not alter M03/M04's frozen non-inference boundary.
No external raw file is bundled in the repository. Fetching a public file is an explicit caller
operation, bounded by the caller and recorded by its source metadata and digest.
