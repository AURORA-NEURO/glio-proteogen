# Public proteomics research foundation

This is additive research infrastructure, not a governed module ABI. It is
deliberately isolated from M03/M04 request and result models while owner
confirmation and scientific validation are pending.

## Scope

The package at `glio_proteogen.research.public_proteomics` provides:

- content-addressed source manifests and bounded local-file verification;
- an HTTPS allow-listed, response-capped client for public PDC study metadata;
- structural FASTA, mzML, and mzIdentML summaries using safe XML parsing;
- deterministic aggregation of source-checked metadata and structural features.

The local parsers do not decode mzML binary measurements, score spectra, assign
peptides, infer proteins/protein groups/proteoforms/isoforms, estimate abundance,
or emit glioma-specific or clinical claims. Counts such as `spectrum_count`,
`peptide_evidence_count`, and `cases_count` are structural or source metadata,
not biological conclusions.

## Captured public record

On 2026-08-17, the public PDC GraphQL endpoint
`https://pdc.cancer.gov/graphql` was queried for `PDC000204` with the bounded
study metadata selection recorded in
`research/fixtures/pdc/pdc000204.manifest.json`. The query digest is
`sha256:f46083cdecd99b08afb71e75a5df313bf58f79510dd58a0698b4f3279b613b37`.
The canonical JSON response digest is
`sha256:ed3fcc96a94e3d14733ce75ca04adc992560aa3ec5f00168c8b77829857b0918`.
The repository contains only this small metadata fixture; no raw cohort files
were downloaded.

PDC metadata is a public source record, not an independently verified
scientific result. Current API usage terms must be checked before any future
retrieval or redistribution.

## Package integrity evidence

`docs/evidence/research_public_proteomics/package.json` is an artifact-bound
receipt for the public-proteomics surface. It records two byte-identical
`SOURCE_DATE_EPOCH=315532800` builds, exact wheel and sdist SHA-256 values,
and the complete sorted archive-member inventory for each artifact. The
standard-library verifier checks the receipt against both candidate files,
rejects duplicate or missing members, and is invoked by the release-evidence
workflow after the candidate wheel is installed into its isolated runtime.
The receipt records the public-proteomics gate. The additive research pipeline additionally has
a locked evaluator for target/decoy competition, shared-peptide ambiguity, group-level FDR, and
replay-bound quantification. Its invariant evaluator rejects accession/decoy flag mismatches,
checks monotone target q-values and decoy exclusion, treats exact-LOQ signals as missing without
imputation, abstains when no decoy/collision winner supplies empirical error evidence, and keeps
shared-only group signal visible while abstaining from a primary estimate.
It does not turn these fixtures into clinical or glioma claims.

## Promotion gate

Before this foundation can feed a governed module, an owner must freeze the
upstream ABI, input catalogue, permitted claims, validation dataset, and
replay/evidence contract. Until then, consumers must treat the aggregate as
research evidence inventory with explicit limitations.
