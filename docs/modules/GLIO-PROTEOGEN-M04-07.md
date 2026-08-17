# GLIO-PROTEOGEN-M04-07 - unsupported-case and abstention router

M04-07 decides whether one already-quality-controlled, harmonized proteoform/isoform-inference
support graph lies inside one reviewed joint support envelope. It evaluates assay, specimen,
disease class,
quality, completeness, platform, reference, and intended-use evidence together and emits only a
support decision, typed abstention reasons, and reviewed remediation paths for the
`protein_rna_discordance` workflow. It does not infer proteins, proteoforms, isoforms, kinase
state, discordance, proteogenomic state, proteotype, or protein-level subtype.

This stateless module consumes full strict M04-04 and M04-06 results alongside compact,
digest-bound receipts derived from those exact results. The full results are retained only so the
compact projections can be rederived and proved exactly; M04-07 does not reinterpret or mutate
them, repair an unreleasable prerequisite, accept caller-authored prerequisite booleans, or
promote a partial envelope match.

## Locked behavior

1. Authorize approved configuration, identity/lineage, provenance, consent, quality, support, and
   intended use before traversing prerequisite receipts, declarations, context receipts, or
   envelope evidence. Denied controls fail closed even when downstream accessors are hostile.
2. Fully admit genuine M04-04 and M04-06 results through strict compact-receipt replay and preserve
   the full results beside the receipts solely to rederive each exact projection. After that full
   admission only, private issued capabilities may reuse the exact prerequisite/request identities
   plus canonical and raw model snapshots while owned output validation compares every field to
   one deterministic bundle sealed by its own snapshot digest. Public and unsealed validation
   always performs full replay.
   Both receipts must be releasable, content-closed, and bound to the same
   proteoform/isoform-inference lineage.
3. Evaluate exactly eight dimensions: `assay`, `specimen`, `disease_class`, `quality`,
   `completeness`, `platform`, `reference`, and `intended_use`.
   Completeness is the conservative minimum of the qualified M04-04 raw-input-completeness
   projection and the accepted M04-06 evaluable-unit fraction. Missing components remain
   indeterminate; an observed value below one envelope's minimum is `outside_domain`.
4. Preserve caller-declared `observed`, `missing`, and `unknown` states. Missing and unknown
   evidence are distinct indeterminate states; neither becomes absence, normality, or a biological
   negative.
5. Require one reviewed envelope to admit the complete joint declaration. Values admitted only by
   different envelopes cannot be combined into support.
6. Enforce platform and reference as all-member constraints. Every declared member must be
   admitted by the same supporting envelope; one accepted member cannot mask an unsupported
   companion.
7. Emit dimension decisions only as `supported`, `outside_domain`, or `indeterminate`; envelope
   decisions only as `confirmed`, `eliminated`, or `provisional`; and the final disposition only as
   `supported` or `abstained`.
8. Emit only the fixed abstention codes `dimension_outside_domain`, `dimension_indeterminate`,
   `prerequisite_unreleasable`, and `joint_combination_outside_domain`, with one reviewed path from
   `correct_support_declaration`, `supply_required_support_evidence`,
   `resolve_upstream_prerequisite`, `select_one_reviewed_joint_envelope`, or
   `request_governed_support_review`.
9. Report every failing dimension in canonical order. Do not collapse failures to an arbitrary
   first error, infer a nearest accepted value, or invent a remediation outside the reviewed
   envelope.
10. Canonicalize set-like declarations, context receipts, envelopes, and evidence so semantic
    reordering produces complete typed-result equality and stable field-owned digests.
11. Use content-derived opaque identifiers with the exact namespaces `request`, `profile`,
    `policy`, `envelope`, `specimen`, `disease`, `reference`, `use`, `reason`, `remediation`,
    `evidence`, `reviewer`, and `route`, each followed by `.` and 64 lowercase hexadecimal
    characters. Projected M04-06 platform levels retain their exact `level.<64 lowercase hex>`
    identifiers.
12. Enforce installed ceilings of 8 dimensions, 4 declared facts, 3 context receipts, 64
    envelopes, 64 values per fact, the exact dependency-bound public M04-06 platform-level and
    analysis-target ceilings, 32 approved versions per domain, 8 evidence references per fact,
    514 abstentions, 46 result evidence references, the 1,000,000 fixed-point scale, and a 4 MiB
    canonical request. Exact maxima are admitted and first excesses fail deterministically.
13. Accept strict immutable JSON only: reject duplicate keys, scalar coercion, non-finite values,
    unknown members or terms, missing required members, stale derived values, contradictory nested
    state, and re-signed forgery.
14. Expose one public operation, `route_proteoform_support`, with HTTP
    `POST /v1/modules/M04-07/support-route`, schema HTTP
    `GET /v1/contracts/M04-07/{name}/schema`, and CLI
    `proteoform-support route|export-schema` boundaries.
15. Recover append-only. Corrected prerequisites, declarations, context receipts, policy, profile,
    or envelope evidence creates a new immutable result with explicit supersession provenance;
    prior results are never edited or silently promoted.
16. Preserve the exact `protein_rna_discordance` parent context while emitting no discordance,
    identity, protein, proteoform, isoform, kinase, proteogenomic-state, proteotype, or
    protein-level-subtype inference. Do not emit abundance, calibrated probability, treatment,
    all-omics fusion, or clinical claims.

## Architecture and authority boundary

Gate G1 installs the dossier's schema-first batch option with quarantine-first deterministic safe
failure. The event-sourced quality service, territory-conditioned subtype, relational registry,
immutable object store, anomaly model, evidence graph, and spatial proteotype field are recorded
as non-executed architecture options. The runtime is stateless and performs no database, network,
registry, object-store, model-service, or external scientific-content access.

A confirmed envelope is a deterministic decision under caller-supplied reviewed metadata. It is
not assay validation, support-domain truth, calibration, transport evidence, scientific inference,
or release authority. All seven uncertainty dimensions remain `not_estimable`; novel or OOD
state, discrepancy, override, claim promotion, release exception, and unresolved conflict require
governed external human review.

## Evidence gate

Gate G1 locks exactly 19 synthetic, non-clinical cases in eight groups allocated
`1/8/2/2/2/1/2/1`: exact joint support; one isolated outside-envelope case for each of the eight
dimensions; typed missing and unknown declarations; unreleasable M04-04 and
M04-06 prerequisite chains; platform/reference all-member enforcement; rejection of a
cross-envelope composite; full result equality under semantic reordering; and consent denial
before hostile evidence traversal. The M04-04 failure also propagates downstream into an
unreleasable M04-06 result, while the M04-06 case keeps M04-04 releasable to isolate its blocker.

These checks prove deterministic routing against a small preregistered envelope corpus. They do
not validate a real support domain, estimate population coverage or transportability, calibrate
probability or uncertainty, qualify an assay, establish biological truth, infer protein-RNA discordance,
or support a clinical decision.

See the [module manifest](M04-07.manifest.md),
[evidence inventory](../evidence/M04-07.md), and
[traceability matrix](../traceability/GLIO-PROTEOGEN-M04-07.csv).
