# External evidence aggregation (research-only)

The glio_proteogen.research.evidence_aggregation module is a bounded evidence
ledger for caller-declared observations from public or local research fixtures.
It addresses an evidence-management problem without pretending to solve
biological inference: each row remains tied to an opaque claim, study/source
identity, method, source SHA-256, and observed byte size.

The ledger accepts exactly four descriptive directions:

- supports: the caller says this receipt is directionally consistent with the
  opaque claim.
- contradicts: the caller says this receipt is directionally inconsistent.
- inconclusive: the receipt does not resolve the direction.
- abstained: the source could not be safely interpreted; a bounded limitation
  is mandatory.

Aggregation never pools numerical estimates. It emits no effect size, p-value,
posterior, confidence interval, disease label, mechanism, glioma-specific
biology, protein/proteoform/isoform inference, or treatment claim.

## Independence and disagreement

minimum_independent_sources is an auditability gate, not statistical power.
Independence is bound to each receipt's `(source_sha256, source_size)` rather
than to caller-chosen labels. Rows with the same receipt identity count as one
independent source even when they use different source_id aliases; every alias
and observation remains in the evidence ledger. A source_id that points to
different receipt identities is rejected as an invalid binding. Two directions
from one receipt identity cause abstained_source_conflict, preserving the
conflict rather than allowing a row count to hide it. Fewer than the requested
independent sources causes abstained_insufficient_independence. A mixture of
directions from independent sources is returned as mixed_direction, not
silently converted into support. A complete all-support ledger is
consistent_support; all contradiction is consistent_contradiction; all
inconclusive is inconclusive.

`independent_source_ids` contains one deterministic representative label per
receipt identity; the complete alias set is retained in the observation ledger
and therefore remains part of the replay digest.

Each aggregate includes a content-addressed EvidenceBundle containing the
canonical observation ledger. Every inner EvidenceRecord digest binds its opaque
evidence ID, source, kind, payload, and quality metadata; changing any of those
fields invalidates the receipt rather than treating provenance labels as mutable
presentation. replay_external_evidence recomputes the bundle,
direction counts, receipt-bound source set, status, and digest and rejects
changed source hashes, directions, source IDs, or thresholds. EvidenceQuality fields describe
receipt auditability and completeness only; they are not a measure of biological
truth.

This remains outside governed M03/M04 execution routes. Promotion would require
an owner-approved ABI covering licensed cohort inputs, source/catalogue identity,
consent and privacy boundaries, allowed claims, validation datasets, and review
or abstention semantics.
