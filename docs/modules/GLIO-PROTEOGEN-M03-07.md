# GLIO-PROTEOGEN-M03-07 - protein-inference support and abstention routing

M03-07 decides whether one already-quality-controlled, harmonized protein-inference support graph
lies inside one reviewed joint support envelope. It evaluates assay, specimen, disease class,
quality, completeness, platform, reference, and intended-use evidence together and emits only a
support decision, typed abstention reasons, and reviewed remediation paths for the
`complex_activity` workflow. It does not infer proteins, proteoforms, kinase state, or complex
activity.

This stateless module consumes full strict M03-04 and M03-06 results alongside compact,
digest-bound receipts derived from those exact results. The full results are retained only so the
compact projections can be rederived and proved exactly; M03-07 does not reinterpret or mutate
them, repair an unreleasable prerequisite, accept caller-authored prerequisite booleans, or
promote a partial envelope match.

## Locked behavior

1. Authorize approved configuration, identity/lineage, provenance, consent, quality, support, and
   intended use before traversing prerequisite receipts, declarations, context receipts, or
   envelope evidence. Denied controls fail closed even when downstream accessors are hostile.
2. Reparse genuine M03-04 and M03-06 results through public compact-receipt helpers and preserve
   the full strict results beside the receipts solely to rederive each exact projection. Both
   receipts must be releasable, content-closed, and bound to the same protein-inference lineage.
3. Evaluate exactly eight dimensions: `assay`, `specimen`, `disease_class`, `quality`,
   `completeness`, `platform`, `reference`, and `intended_use`.
   Releasable canonical prerequisites make completeness exactly 1,000,000; an unavailable or
   below-threshold completeness path is therefore a prerequisite abstention with an indeterminate
   completeness assessment, never a fabricated `outside_domain` measurement.
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
    characters. Projected M03-06 platform levels retain their exact `level.<64 lowercase hex>`
    identifiers.
12. Enforce installed ceilings of 8 dimensions, 4 declared facts, 3 context receipts, 64
    envelopes, 64 values per fact, 512 platform levels, 32 approved versions per domain, 8 evidence
    references per fact, 514 abstentions, 46 result evidence references, the 1,000,000 fixed-point
    scale, and a 4 MiB canonical request. Exact maxima and first excesses fail deterministically.
13. Accept strict immutable JSON only: reject duplicate keys, scalar coercion, non-finite values,
    unknown members or terms, missing required members, stale derived values, contradictory nested
    state, and re-signed forgery.
14. Expose one public operation, `route_protein_inference_support`, with HTTP
    `POST /v1/modules/M03-07/support-route`, schema HTTP
    `GET /v1/contracts/M03-07/{name}/schema`, and CLI
    `protein-inference-support route|export-schema` boundaries.
15. Recover append-only. Corrected prerequisites, declarations, context receipts, policy, profile,
    or envelope evidence creates a new immutable result with explicit supersession provenance;
    prior results are never edited or silently promoted.
16. Preserve the exact `complex_activity` parent context while emitting no complex-activity,
    identity, protein, proteoform, or kinase inference. Do not emit abundance, calibrated
    probability, subtype, proteotype, treatment, or clinical claims.

## Evidence gate

Gate G1 locks exactly 19 synthetic, non-clinical cases in eight groups allocated
`1/8/2/2/2/1/2/1`: exact joint support; seven isolated outside-envelope dimensions plus the
reachable completeness boundary; typed missing and unknown declarations; unreleasable M03-04 and
M03-06 prerequisite chains; platform/reference all-member enforcement; rejection of a
cross-envelope composite; full result equality under semantic reordering; and consent denial
before hostile evidence traversal. The M03-04 failure also propagates downstream into an
unreleasable M03-06 result, while the M03-06 case keeps M03-04 releasable to isolate its blocker.

These checks prove deterministic routing against a small preregistered envelope corpus. They do
not validate a real support domain, estimate population coverage or transportability, calibrate
probability or uncertainty, qualify an assay, establish biological truth, infer complex activity,
or support a clinical decision.

See the [module manifest](M03-07.manifest.md),
[evidence inventory](../evidence/M03-07.md), and
[traceability matrix](../traceability/GLIO-PROTEOGEN-M03-07.csv).
