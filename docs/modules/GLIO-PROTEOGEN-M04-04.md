# GLIO-PROTEOGEN-M04-04 - quality metric computation

M04-04 computes deterministic fixed-point quality metrics for the four validated M04-03
proteoform raw-input roles. It consumes the exact full public M04-03 result and caller-declared
aggregate facts, selects one reviewed assay profile per role, and emits a typed quality profile
supporting the parent `protein_rna_discordance` workflow. It never opens an external scientific
content artifact, identifies a protein, proteoform, isoform, or PTM, localizes a modification,
or makes a biological, treatment, or clinical inference.

## Locked behavior

1. Authorize approved configuration, resolved identity and lineage, provenance, consent,
   quality, support, and intended use before traversing the request, embedded raw-input result,
   policy, fact ledger, or nested values. Built-in dict access bypasses subclass overrides;
   arbitrary mappings reject, ordinary exceptions fail closed, and `BaseException` propagates.
2. Bind `compute_proteoform_quality_metrics`, contract version 1.0.0, and one identical opaque
   request identifier across request and context. Replay the exact full public M04-03 result,
   transitively retaining genuine public M01-02, M04-01, and M04-02 results. Compact or re-signed
   substitutes reject.
3. Bind context identity to the M04-03 receipt identity digest, quality evidence to the M04-03
   result digest, support evidence to its receipt digest, intended use to its receipt, and
   approved configuration to the M04-04 configuration digest. Policy, raw-result, ledger, and
   completion chronology close exactly.
4. A validated M04-03 result requires one ledger. A quarantined or abstained M04-03 result
   requires no ledger and returns the corresponding typed safe failure before ledger traversal.
5. A ledger contains exactly one role fact for each validated input. Each fact binds the exact
   role, input identifier, validated-input digest, document digest, and evidence. A stale
   self-digest is structural rejection; an otherwise valid semantic input or document binding
   mismatch quarantines with `fact_ledger_binding_mismatch` and emits zero metrics.
   Each fact input identifier remains the exact opaque upstream `input.*` identifier.
6. Keep all aggregate counts within 0 through 9,223,372,036,854,775,807. Numerators never exceed
   denominators; parsed never exceeds declared, valid never exceeds parsed, and detection counts
   partition their eligible count. Counts are scalar declarations and never allocation sizes.
7. Compute the eight role metrics as the exact declared numerator/denominator ratios. Values use
   integer parts per million with round-half-up:
   `(numerator * 1_000_000 + denominator // 2) // denominator`. Floats are never used.
8. A zero denominator yields no value and `not_evaluable`; it never becomes zero or a negative.
   Non-observed states carry no numerator, denominator, or value. `not_applicable` maps only to
   `not_applicable`; other non-observed states map to `not_evaluable`.
9. Only `detection_limit_burden` may be censored. Censoring is present exactly when the below-limit
   count is positive, and it retains the exact detection ratio and censored count. Missing,
   unsupported, indeterminate, and censored evidence never becomes a negative observation.
10. Require four through 32 reviewed assay profiles, all four roles covered, disjoint match
    domains, and at most 32 approved versions per profile. Proteome applicability is required
    only for the proteome role. Each profile contains exactly one threshold for each metric.
11. `at_least` passes at or above the pass threshold, warns between warning and pass, and fails
    below warning. `at_most` passes at or below pass, warns through warning, and fails above it.
    Status compares the already round-half-up integer `value_ppm`, not a cross-product;
    for example, 2/3 becomes 666,667 ppm and passes an `at_least` threshold of 666,667.
    Direction and threshold ordering are closed by the contract.
12. Emit all four assay-quality objects and all 32 metrics when ledger bindings and profile
    selection close, including governed threshold quarantine. Upstream safe failure, semantic
    ledger-binding failure, or unsupported profile emits zero assay-quality objects and metrics.
13. Every metric failure quarantines. Required warnings quarantine. Required missing,
    unsupported, indeterminate, or zero-denominator metrics abstain. Optional warnings are
    retained and limit support. Quarantine takes precedence over abstention and record-only
    findings.
14. Cross-metric contradictions, including reference or detection eligibility above observed
    feature counts, quarantine rather than clipping or repair. Findings are unique and canonical,
    and their identifiers derive from their exact content. Receipt disposition is rederived from
    its canonical finding-code set; no publicly valid zero-digest sentinel exists.
15. A clean qualified result is supported as `proteoform_quality_qualified`. A qualified result
    with an optional warning is limited as `proteoform_quality_qualified_with_optional_warning`.
    Quarantine requires review; abstention is unsupported. Human review is required for every
    nonqualified result and every optional warning.
16. Return only current-layer evidence: seven controls, one policy record, 4-32 profile records,
    an optional ledger record, and four fact records, for exactly 12-45 records. Upstream evidence
    remains inside the embedded result and is not duplicated. Reusing one evidence
    identity/version with conflicting content rejects.
17. Emit all seven uncertainty dimensions as `not_estimable`, with no probability. Fixed-point
    aggregates provide no measurement-error, sampling, parameter, model-form, identification,
    support-authority, or transport distribution. Site and assay transport require external
    validation.
18. Emit exactly three limitations: `deterministic_aggregate_quality_metrics_only`,
    `external_measurements_controls_and_authority_not_authenticated`, and
    `no_proteoform_discordance_or_clinical_inference`.
19. Fully rederive metrics, findings, disposition, receipt, support, uncertainty, provenance,
    evidence, limitations, review, completion, and result digest during result validation.
    Canonical semantic reordering preserves complete result equality; re-signed derived regions
    reject.
20. Use only opaque caller-reflected identifiers in the namespaces `request`, `actor`,
    `decision`, `policy`, `profile`, `ledger`, `fact`, `evidence`, and `reviewer`, followed by 64
    lowercase hexadecimal characters. Result, activity, and finding identifiers use
    `result.m0404.*`, `activity.m0404.*`, and `finding.m0404.*`.
21. Export exactly 13 strict JSON Schema 2020-12 contracts: request, output, policy, threshold,
    assay-profile, fact-counts, fact-states, role-facts, fact-ledger, metric, assay-quality,
    finding, and receipt.
22. Expose schema GET at `/v1/contracts/M04-04/{name}/schema` and metadata-only computation POST at
    `/v1/modules/M04-04/quality-metric-computation`. Expose CLI
    `proteoform-quality export-schema NAME` and
    `proteoform-quality compute REQUEST --output RESULT`.
23. CLI JSON is duplicate-free and strict, with the 4 MiB cap enforced before decoding. Output
    must be a new regular path: existing, symlink, junction, and reparse targets reject, and
    publication is atomic.
24. Recover append-only. A corrected request may name a superseded result digest but never
    overwrites, relabels, repairs, deduplicates, or silently promotes upstream evidence.

Every output retains `protein_rna_discordance` only as parent context. It emits no discordance,
proteogenomic state, proteotype, protein-level subtype, identity, consent, protein, proteoform,
isoform, modification localization, kinase activity, CN-to-protein regression, all-omics fusion,
treatment recommendation, upstream mutation, or executed-model claim.

## Architecture and authority boundary

The dossier records an event-sourced quality service, a schema-first batch service, and a
quarantine-first pipeline together with PTM-aware, probabilistic, and isoform-aware model names.
Gate G1 installs only deterministic schema-first fixed-point arithmetic and quarantine-first safe
failure. It installs no event log, database, object store, anomaly learner, evidence graph,
probabilistic model, quantification model, weights, fitting, or mutable persistence.

The role-fact ledger is caller-declared aggregate metadata. Its digests make local replay
deterministic and tamper-evident under the installed rules; they do not authenticate a
measurement, laboratory, reviewer, identity, assay execution, external content, or scientific
truth. M04-04 never dereferences an M04-03 `content_reference`.

## Evidence gate

Gate G1 locks exactly 72 unique synthetic, non-clinical cases in eight groups allocated
8/9/9/9/8/8/8/13: canonical computation; fact-ledger and metric math; profiles, versions, and
units; thresholds, support, and disposition; upstream closure and safe failure; nonmutation,
evidence, and authority; uncertainty, provenance, and result replay; and strict boundary,
interfaces, and caps. Declared and executed case sets must match exactly.

The representative benchmark constructs a genuine M01-02 through M04-03 chain and the maximum
supported metadata shape—32 profiles, 256 thresholds, four facts, 32 metrics, and 45 evidence
records—outside measurement. After one untimed warm-up, it measures exactly 25 public
`compute_proteoform_quality_metrics` calls. Mean latency must be at most 500 milliseconds and p95
at most 750 milliseconds. These are software regression budgets, not scientific validation.

See the [module manifest](M04-04.manifest.md),
[evidence inventory](../evidence/M04-04.md), and
[traceability matrix](../traceability/GLIO-PROTEOGEN-M04-04.csv).
