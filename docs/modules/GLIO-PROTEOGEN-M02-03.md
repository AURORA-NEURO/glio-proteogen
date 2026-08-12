# M02-03: raw-format ingestion and parser

M02-03 validates the bounded raw-input bundle used by peptide-spectrum and identification QC.
It reuses M01-03's strict byte parser for checksum verification, gzip handling, content-based
format/version detection, structural validation, and typed per-source diagnostics. M02-03 adds
only identification-specific roles, required-role/cardinality rules, and role-to-format policy.

## Ingestion boundary

1. Require consent and accepted configuration, provenance, quality, support, and intended-use
   controls before reading source mappings or hashing bytes.
2. Bind every request to a versioned role policy and the underlying bounded M01-03 policy.
3. Read each source once, verify the exact declared length and checksum, and detect content rather
   than trusting the filename extension.
4. Preserve M01-03 source results verbatim. M02-03 never relabels malformed, missing, unsupported,
   or rejected content as a negative biological finding.
5. Require explicit policy for spectra, peptide identifications, sequence databases, genomic
   variants, transcript annotations, and PTM annotations. Optional roles remain explicitly
   optional.
6. Quarantine missing required roles, role cardinality failures, and role/format mismatches.
7. Emit metadata, digests, diagnostics, and the standard evidence envelope only. Raw bytes,
   sequences, variants, spectra, paths, and biological interpretations never enter the result.

The implementation is a stateless deterministic wrapper. It does not duplicate the parser, keep
an object store, create an event ledger, infer peptides or proteins, build a protein-complex graph,
own kinase activity, fuse omics, or recommend treatment.

## Evidence gate

Gate G0 uses a small synthetic corpus covering a conformant required bundle, gzip magic,
extension/content disagreement, checksum rejection, malformed content quarantine, missing roles,
role/format mismatch, and authorization before byte traversal. Replay also checks full-result
order determinism and the closed metadata-only boundary. One broad batch benchmark is a generous
regression tripwire, not a scientific or asymptotic performance claim.

These checks establish deterministic behavior for synthetic fixtures and one pinned role policy.
They do not establish assay validity, peptide-identification correctness, biological validity,
protein subtype, cohort transportability, clinical readiness, or treatment suitability.

See the [module manifest](M02-03.manifest.md),
[evidence inventory](../evidence/M02-03.md), and
[traceability matrix](../traceability/GLIO-PROTEOGEN-M02-03.csv).
