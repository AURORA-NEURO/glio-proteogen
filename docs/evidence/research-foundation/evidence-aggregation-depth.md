# Research evidence aggregation depth

This receipt documents a research-only integrity hardening tranche. It does not
change a governed module ABI and does not turn evidence quality into a biological
confidence score.

## Source independence and weighting

`EvidenceRecord.source` is the provenance grouping key for quality aggregation.
If one source emits several projections, such as a matrix, QC summary,
provenance receipt, and descriptive contrast, the projections are averaged within
that source group. The record's caller-declared `independent_sources` count is
then applied once to that group. The bundle's `quality_source_groups` field
exposes the number of groups used by the weighted projection. This prevents a
source from increasing its evidence weight merely by emitting more derived
views. Quality records from one source must agree on their declared independent
source count; a conflict is rejected rather than guessed.

The count remains caller-declared provenance metadata. It is not inferred from
sample names, record count, or repeated aliases, and it is not statistical power.

## Identity, replay, and abstention

Evidence IDs, source IDs, and kinds are bounded non-whitespace identifiers and
are included in each record digest. The complete record projection, quality
summary, limitations, and source-group count are included in the outer bundle
digest and are recomputed by `verify_evidence_bundle`.

An `abstained` quality record must carry zero completeness. A source that cannot
support its requested observation therefore cannot present a complete-looking
quality score. The record remains visible for audit and replay, while consumers
must inspect the explicit abstention status before using any projection.

## Focused adversarial gate

The regression suite covers source-group de-duplication, conflicting source
independence declarations, identity-field bounds, abstention completeness, inner
record digest binding, outer summary replay, and external-evidence abstention.
The implementation is isolated under `glio_proteogen.research`; no M03/M04
contract, route, or result model is modified.
