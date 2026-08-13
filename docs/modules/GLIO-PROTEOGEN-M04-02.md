# GLIO-PROTEOGEN-M04-02 - proteoform identity and lineage reconciliation

M04-02 reconciles already-governed physical identity and lineage with the artifacts used beneath
C04 Proteoform/isoform inference. It consumes the exact full M01-02 identity resolution and the
exact full M04-01 protocol-conformance result, then closes five opaque artifact roles and one
four-source derivation without changing either upstream object. It emits only an immutable
identity-resolution object and separate physical/artifact lineage graph supporting the parent
protein_rna_discordance workflow. It never establishes a real identity, observes a protein or
proteoform, computes copy-number or protein-RNA discordance, or makes biological or clinical
inference.

## Locked behavior

1. Authorize approved configuration, resolved identity/lineage, provenance, consent, quality,
   support, and intended use before traversing the embedded identity result, protocol result,
   policy, artifact claims, derivation, or nested mappings. Each denied control fails closed with
   zero governed traversal. Built-in mapping access ignores hostile dict-subclass overrides;
   ordinary exceptions fail closed, while BaseException propagates unchanged.
2. Bind the request and context to operation reconcile_proteoform_identity_lineage, contract
   version 1.0.0, and one identical opaque request identifier. The context identity digest equals
   both the M01-02 resolution_digest and the M04-01 receipt identity_subject_digest.
3. Require the exact full, self-validating public M01-02 IdentityLineageResolution and exact full
   M04-01 ProteoformProtocolConformanceResult. Revalidation replays both envelopes; a compact
   M04-01 receipt alone is insufficient. Self-inconsistent, stale, or re-signed upstream content
   is rejected rather than refreshed.
4. Bind the current intended-use evidence digest to the M04-01 receipt
   intended_use_evidence_digest. Require M01-02 completion no later than M04-01 completion and
   M04-01 completion no later than M04-02 completion; policy review also precedes M04-02
   completion. Approved-configuration evidence binds exactly to the configuration digest derived
   from the reviewed M04-02 policy.
5. Preserve all seven governed physical kinds—patient, specimen, aliquot, section, analyte, run,
   and derived object. Every artifact claim anchors to a derived object reachable on a governed
   patient-to-derived-object path. M04-02 reuses exact upstream entity and subject-component
   identifiers and never invents, merges, relabels, repairs, or selects an identity.
6. Keep the upstream physical graph distinct from the local artifact DAG. The five artifact roles
   are mass_spectrometry_proteome_manifest, genome_manifest, transcriptome_manifest,
   ptm_annotation_manifest, and protein_rna_discordance_input_bundle. Role and media type agree
   exactly, and every non-secret submitted artifact declaration remains immutable.
7. Require between five and 256 claims, including exactly one bundle claim and at least one claim
   for each of the other four roles. Require exactly one derivation targeting the bundle. Its
   source identifiers equal all non-bundle claims, cover all four source roles, and contain between
   four and 255 unique entries. Reject disconnected or unreferenced claims, dangling or self
   endpoints, duplicate sources, multiple bundle targets, and unapproved methods.
8. Resolve each claim's subject components from its exact upstream anchor. A declared-versus-
   resolved mismatch records identity_swap; a derivation subject union spanning more than one
   component records cross_patient_link; differing anchor/path pairs within an assembly record
   artifact_lineage_collision. These findings quarantine without relabelling a claim, rewriting
   an edge, or synthesizing a patient assignment.
9. Record binding_scope_collision when multiple declarations share one role and anchor. Record
   artifact_identity_collision when one artifact identifier/version pair carries differing
   digest or media declarations. Record duplicate_content_retained when a digest appears in
   distinct claims. Duplicate content is permitted and retained; M04-02 never deduplicates it or
   chooses an authoritative copy. Quarantine takes precedence over abstention.
10. Bind every producer declaration to the exact upstream identity result, M04-01 result,
    reference bundle, and coordinate policy. Drift remains separate as producer_identity_drift,
    producer_protocol_drift, producer_reference_bundle_drift, and
    producer_coordinate_policy_drift.
11. Preserve the closed evidence states observed, missing, indeterminate, unsupported, and
    redacted. Non-observed evidence produces typed abstention without deleting components or
    converting missing evidence into protein absence. A valid unresolved M01-02 result also
    abstains; a valid quarantined M04-01 result quarantines. These are valid safe-failure results,
    not malformed requests.
12. Emit only reconciled, quarantined, or abstained. Findings use only record, quarantine, or
    abstain and the exact 14 installed codes. duplicate_content_retained maps only to record;
    upstream_identity_unresolved, identity_not_evaluable, and artifact_evidence_not_evaluable map
    only to abstain; every other code maps only to quarantine. The receipt carries the canonical
    unique set of finding codes, and both receipt and result disposition derive from those codes.
    Reconciled results are supported, quarantined results require review, and abstained results
    are unsupported. Review is required exactly when the disposition is not reconciled.
13. Emit all seven uncertainty dimensions as not_estimable. Return exactly three limitations:
    deterministic_identity_lineage_reconciliation_only,
    caller_declared_authority_not_authenticated, and
    no_identity_protein_discordance_or_clinical_inference.
14. Index exactly seven local control-evidence records, one policy record, one through 64 approved
    method records, five through 256 claim records, and one derivation record: 15 through 329 total.
    Embedded upstream evidence remains inside the embedded results and is not duplicated.
15. Enforce a maximum of 256 subject components, 64 approved methods, 2,435 findings, and a
    4,194,304-byte canonical request. The maximum structurally accepted request executes
    deterministically and is quarantined when its repeated binding scopes trigger the installed
    collision rules; every first excess is rejected before canonical graph work.
16. Accept strict immutable JSON only. Reject duplicate keys, scalar coercion, unknown fields or
    terms, wrong role media types, duplicate semantic identifiers, inconsistent nested results,
    stale derived values, and re-signed graph, finding, provenance, evidence, receipt, or result
    forgery. Canonical ordering never conceals a duplicate.
17. Canonicalize every semantic tuple. Reordering yields complete request, graph, findings,
    receipt, result, and digest equality. Result identifiers derive as
    result.m0402.<request-digest-hex> and provenance activities analogously as
    activity.m0402.<request-digest-hex>; no public zero-digest sentinel is accepted.
18. Use opaque local identifiers only in the namespaces request, actor, decision, policy, method,
    claim, derivation, evidence, and reviewer, each followed by exactly 64 lowercase hexadecimal
    characters. Recursively exclude direct identifiers, raw identity tokens, sequences,
    accessions, raw copy-number/RNA/protein abundance, PTM sites, activity, subtype, proteotype,
    treatment, and clinical claims.
19. Export exactly eight JSON Schema 2020-12 contracts: request, output, policy, artifact-claim,
    derivation, graph, finding, and receipt. Expose public Python
    reconcile_proteoform_identity_lineage, HTTP
    POST /v1/modules/M04-02/identity-lineage-reconciliation, schema HTTP
    GET /v1/contracts/M04-02/{name}/schema, and CLI
    proteoform-lineage reconcile REQUEST / proteoform-lineage export-schema NAME with complete
    typed parity. There is no binary or filesystem ingestion route.
20. Recover append-only. A corrected request may name a superseded result digest, but it never
    mutates, deletes, re-signs, relabels, deduplicates, or silently promotes prior evidence.
    Critical discrepancy, novel/OOD state, support override, claim promotion, release exception,
    or unresolved biological conflict remains external human-review work.

Every receipt and result keeps protein_rna_discordance only as the parent context and sets all
authority flags false: no parent output, proteogenomic state, proteotype, protein-level subtype,
identity, consent, protein, proteoform, kinase state, CN-to-protein regression, all-omics fusion,
treatment recommendation, or upstream mutation is produced.

## Architecture and authority boundary

The dossier names event-sourced quality plus a transcript-protein residual model as primary,
schema-first batch plus CN-to-protein regression as alternate, and quarantine-first deterministic
plus CN-to-protein regression as fallback. Gate G0 selects only the deterministic, stateless,
schema-first reconciliation boundary with quarantine-first failure semantics. M04-02 installs or
executes no residual model, CN-to-protein regression, learner, estimator, event store, mutable
registry, database, object store, or filesystem workflow. The architecture names remain manifest
declarations, not executed scientific methods.

Caller-declared digests and review records make the reconciliation reproducible and tamper-evident
under the installed canonical rules. They do not authenticate an issuer, prove identity or
reference truth, confer review authority, or attest laboratory execution. The exclusive
technology outputs—proteogenomic state, proteotype, and protein-level subtype—remain governed
downstream outputs. KINOPHOS retains kinase-state ownership; generic all-omics fusion and direct
treatment recommendation are prohibited.

## Evidence gate

Gate G0 locks exactly 70 unique synthetic, non-clinical cases in eight groups allocated
6/6/7/6/8/9/8/20: canonical reconciliation; swaps and nonmutation; collision and duplicate
retention; cross-patient detection; malformed shape; upstream and producer drift; evidence-state
and authority ceilings; and strict authorization, privacy, capacity, ordering, and forgery
boundaries. The executable builder must call public M01-02 first, bind its exact digest into a
genuine M04-01 request, call public M04-01, and only then build M04-02. Handwritten upstream result
envelopes are prohibited.

The representative benchmark prepares the genuine seven-kind upstream chain, five claims, and
one exact four-source assembly before timing, performs one untimed warm-up, and then measures
exactly 25 public reconciliation calls. Mean latency must be at most 400 milliseconds and p95 at
most 600 milliseconds. The 256-claim maximum belongs to capacity evaluation, not the representative
benchmark. These limits are software regression tripwires, not evidence of identity truth,
scientific performance, uncertainty calibration, biological validity, transportability, or
clinical readiness.

See the [module manifest](M04-02.manifest.md),
[evidence inventory](../evidence/M04-02.md), and
[traceability matrix](../traceability/GLIO-PROTEOGEN-M04-02.csv).
