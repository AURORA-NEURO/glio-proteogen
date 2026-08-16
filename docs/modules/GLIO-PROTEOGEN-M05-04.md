# GLIO-PROTEOGEN-M05-04 - quality metric computation

M05-04 computes deterministic fixed-point aggregate quality metrics beneath the C05 PTM
localization interface. It strictly replays the complete M05-03 result, binds a reviewed
assay-quality policy and an optional four-role fact ledger, and emits only a typed quality profile
supporting the parent `variant_peptide` workflow. It does not open external content, inspect raw
rows or spectra, localize a modification, infer protein or PTM biology, execute a model, emit the
parent object, claim KINOPHOS ownership, fuse omics, recommend treatment, or make a clinical claim.

## Locked behavior

1. Inspect approved configuration, resolved identity/lineage, provenance, consent, quality,
   support, and intended-use controls before traversing the embedded M05-03 result or fact ledger.
   Every denial fails closed with zero ledger access. Ordinary exceptions fail closed and
   `BaseException` propagates.
2. Bind operation `compute_ptm_localization_quality_metrics`, contract version 1.0.0, and one
   exact opaque request identifier across request and context. Strictly replay the complete public
   M05-03 result; a compact receipt or re-signed semantic substitute rejects.
3. Bind identity, upstream result, upstream receipt, intended use, reviewed policy, configuration,
   seven control decisions, and chronology exactly. A validated M05-03 result requires a ledger;
   a quarantined or abstained result prohibits one and is handled without ledger traversal.
4. Accept exactly four roles: mass-spectrometry proteome, genome, transcriptome, and PTM
   annotations. A ledger contains exactly one fact per role and binds the exact input identifier,
   validated-input digest, document digest, M05-03 result digest, and M05-03 receipt digest.
5. Use 4-32 reviewed profiles. Each role selects exactly one disjoint profile by role, proteome
   assay/support axes, control applicability, assay protocol version, specimen-processing version,
   and unit-system version. A profile owns exactly eight thresholds, one per metric.
6. Compute eight metrics per role and exactly 32 metrics for a qualified shape: raw-input
   completeness, valid-record coverage, assay-feature coverage, reference-mapping coverage,
   detection-limit burden, control-material recovery, sample-context binding coherence, and
   cross-input consistency.
7. Use integer round-half-up parts per million on closed numerator/denominator partitions.
   Detection-limit burden is the only at-most metric and the only metric that may retain a
   positive censored count. A zero denominator remains not evaluable; missing or unsupported
   evidence never becomes a zero or negative observation.
8. Emit only qualified, quarantined, or abstained. Binding, version, required warning, threshold
   failure, or cross-metric inconsistency quarantines. Missing, unsupported, or not-evaluable
   required evidence abstains. Quarantine has precedence. An optional warning retains qualified
   disposition but limits support and requires review.
9. Preserve every upstream and local evidence occurrence, including duplicate content with
   distinct identity. Never deduplicate, relabel, mutate, repair, infer authority, or erase
   disagreement.
10. Safe upstream failure emits zero profiles, metrics, and assay-quality regions and exactly 12
    local evidence records. The maximum qualified shape is 32 profiles, 256 thresholds, four
    facts, 32 metrics, and 45 evidence records. Every result has exactly three limitations.
11. Cap strict JSON ingress at 4,194,304 bytes and reject the first excess before validation.
    Unknown fields, scalar coercion, duplicate keys, arbitrary mappings/sequences, container
    subclasses, stale capabilities, and mutated tokens fail closed.
12. Seal typed and JSON admission capabilities to exact identity and canonical byte snapshots.
    Reuse is allowed only while the request, embedded M05-03 result, derived digests, and issuance
    registry all remain unchanged.
13. Fully rederive profile selection, metrics, findings, disposition, assay-quality regions,
    receipt, support, uncertainty, provenance, evidence, limitations, review flag, completion
    time, and result digest during result validation. Every re-signed derived forgery rejects.
14. Export exactly 13 JSON Schema 2020-12 contracts. Expose HTTP schema GET and strict execution
    POST `/v1/modules/M05-04/quality-metric-computation`. Expose CLI
    `ptm-localization-quality compute REQUEST --output RESULT` and
    `ptm-localization-quality export-schema NAME`. Python, service, plugin, API, and CLI results
    are exactly equal.
15. Recover append-only. A corrected request may name a superseded result digest, but no path
    overwrites prior evidence or output. Critical discrepancy, novel/OOD state, support override,
    claim promotion, release exception, or unresolved biological conflict remains external review.

## Architecture and authority boundary

The dossier names an event-sourced quality service with a structure-aware proteoform model, a
schema-first batch alternative, and a quarantine-first deterministic fallback. Gate G1 installs
the deterministic schema-first/fixed-point boundary and quarantine-first safe-failure semantics.
It installs no event log, mutable database, object store, probabilistic model, structure model,
weights, anomaly learner, calibration fit, or external lookup. Architecture/model names remain
manifest declarations rather than executed methods.

All data is synthetic, non-clinical, opaque aggregate metadata. Checksums and caller-declared
review records make local replay deterministic and tamper-evident under installed rules; they do
not establish assay truth, scientific validity, reviewer authority, identity, consent validity,
transportability, calibration, biological correctness, or clinical readiness.

## Evidence gate

Gate G1 locks exactly 72 unique cases in eight groups allocated 8/9/9/9/8/8/8/13. The evaluator
binds the raw fixture digest, requires exact declared/executed case equality, and exercises genuine
public M01-02 through M05-03 construction before M05-04. The representative benchmark builds the
maximum supported metadata shape outside timing, performs one untimed warm-up, and measures exactly
25 public calls. Mean latency must be at most 500,000,000 ns and nearest-rank p95 at most
750,000,000 ns. The report retains all samples and binds request/result byte sizes and digests.

See the [module manifest](M05-04.manifest.md),
[evidence inventory](../evidence/M05-04.md), and
[traceability matrix](../traceability/GLIO-PROTEOGEN-M05-04.csv).
