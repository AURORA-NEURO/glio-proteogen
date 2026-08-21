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

Aggregation also checks that each manifest media type is compatible with the
structural format being summarized (while retaining `application/octet-stream`
for caller-declared binary sources). A content hash/length match alone cannot
justify recording a FASTA summary under an mzML media declaration.

The local parsers do not decode mzML binary measurements, score spectra, assign
peptides, infer proteins/protein groups/proteoforms/isoforms, estimate abundance,
or emit glioma-specific or clinical claims. Counts such as `spectrum_count`,
`peptide_evidence_count`, and `cases_count` are structural or source metadata,
not biological conclusions. Structural receipt fields require exact integer
counts and byte lengths; boolean values are rejected rather than coerced through
Python's `bool`-is-an-`int` behavior.

Catalog snapshots fail closed when any returned file declares a different PDC
study than the requested study. This prevents a mixed-study metadata response
from being archived under the requested study identity before any raw-file
receipt is created.

Metadata snapshots also retain the client endpoint only when it is an
allow-listed HTTPS PDC host with no embedded credentials, query parameters, or
non-default port. Query parameters are rejected because they can carry bearer
tokens that must never enter replayable provenance.
This keeps a caller-constructed snapshot from presenting off-domain metadata as
an authenticated PDC source in downstream evidence.
The metadata client's timeout and response-byte cap also require strict numeric
types; boolean values are rejected rather than coerced through Python's
`bool`-is-an-`int` relationship.
The bounded study-file snapshot limit follows the same strict integer rule, so
boolean values cannot be interpolated into the GraphQL request as a row count.

Raw-file receipts apply the same check to caller-constructed snapshots: every
file in the captured inventory must belong to the snapshot study, even when the
selected file itself matches. This prevents a valid file receipt from carrying
an otherwise contaminated cross-study catalog inventory.

Catalog file declarations require an exact non-negative integer byte size at
construction. Boolean values are rejected rather than being treated as `0` or
`1` through Python's `bool`-is-an-`int` relationship, preserving the exact-size
source binding used by raw-file receipts.

Raw-file receipts also require the captured catalog snapshot to remain bound to
the canonical PDC study locator and to contain typed, non-negative count rows;
file declarations must carry the bounded `PDC` accession form, so forged
catalog projections cannot be promoted to source evidence.

Verified PDC bytes are copied with a progress-checked destination contract;
zero-progress or invalid short writes fail the retrieval instead of returning a
successful receipt for a truncated caller-owned file.

PDC signed download URLs are runtime-only bearer credentials. The downloader
uses the URL from the in-memory `PdcFile`, but receipt, snapshot, pipeline
configuration, and evidence projections retain the stable `signed_url` field as
`null`; this prevents expiring credentials from being persisted or copied into
replay artifacts while leaving source identity bound to catalog metadata and
observed bytes. Token rotation for the same catalog declaration is therefore
accepted without changing the source receipt or replay digest.

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

Structural aggregation is complete with respect to the caller's manifest: every
non-PDC source declared there must provide a matching local format summary.
Omitting a declared FASTA, mzML, or mzIdentML feature is rejected instead of
silently understating the aggregate's local-source count.

The public `FeatureRecord` and `EvidenceAggregate` constructors apply the same
closure as the factory. Feature keys, source records, and structural counts must
be unique and canonically ordered; source formats and SHA-256 identities are
validated; counts must agree with the recorded byte features; fixed limitations
cannot be replaced; and `aggregate_id` must hash the complete evidence
projection. This prevents a caller from turning a hand-built or replayed
receipt with silently collapsed fields or forged counts into structural evidence.

## Promotion gate

Before this foundation can feed a governed module, an owner must freeze the
upstream ABI, input catalogue, permitted claims, validation dataset, and
replay/evidence contract. Until then, consumers must treat the aggregate as
research evidence inventory with explicit limitations.
