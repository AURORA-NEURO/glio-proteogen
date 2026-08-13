# M03-02: protein-inference identity and lineage reconciliation

M03-02 closes the identity and lineage boundary for the protein-inference workflow beneath C03.
It receives one immutable M01-02 identity resolution, one exact self-validating M03-01 protocol result, and
digest-bearing workflow artifacts. It verifies that the complete patient, specimen, aliquot,
section, analyte, run, and derived-object chain remains connected to a well-formed artifact DAG.
It detects swaps, identifier collisions, duplicate-content assignments, cross-patient propagation,
malformed derivations, and upstream or protocol drift. It emits only an immutable reconciliation
result and a canonical lineage presentation that supports the parent `complex_activity` workflow.

## Reconciliation boundary

1. Authorize approved configuration, identity/lineage, provenance, consent, quality, support, and
   intended use before traversing lineage nodes, artifact bindings, or concordance declarations.
2. Bind the request to exact, successfully reconstructed M01-02 and M03-01 results. A digest copied
   into context is not enough: the embedded upstream objects, their self-digests, their decisions,
   and the request bindings must agree. A valid unresolved M01-02 result yields typed abstention and
   a valid nonconformant M03-01 result yields typed quarantine; neither is an invalid request.
3. Support the seven governed physical entity kinds: patient, specimen, aliquot, section, analyte,
   run, and derived object. The canonical profile exercises the complete linear route; other valid
   requests may use any governed M01-02 path shape. M03-02 reuses opaque upstream entity and
   subject-component identifiers; it never invents, renames, merges, or repairs them.
4. Keep the physical lineage graph distinct from the artifact DAG. Physical derivation establishes
   chain of custody; artifact edges establish content-addressed workflow dependencies. An artifact
   digest may be retained in more than one binding without collapsing the bindings or selecting an
   authoritative copy.
5. Detect swaps and scoped identifier collisions without relabelling upstream material. A swap,
   collision, ambiguous producer, cross-patient ordinary derivation, or propagated contaminated
   descendant remains explicit and reviewable.
6. Validate the artifact DAG as a closed, acyclic graph with known endpoints, permitted roles,
   deterministic topological order, and complete roots. Dangling edges, cycles, self-dependencies,
   duplicate edge identifiers, and unapproved multi-producer shapes fail closed. The closed profile
   contains exactly four roles: `peptide_evidence_manifest` feeds `protein_group_manifest`, which
   feeds `ambiguity_manifest`; `complex_activity_input_bundle` has exactly one protein-group parent
   and one ambiguity parent.
7. Bind the graph to the exact M03-01 protocol and search-space identity. Stale upstream identity,
   protocol, search-space, or graph digests cannot be silently refreshed, substituted, or treated
   as an equivalent version.
8. Treat copy-number-to-protein concordance as identity-control evidence only. `concordant`,
   `discordant`, `missing`, `indeterminate`, and `unsupported` remain separate typed states.
   Concordance may corroborate, quarantine, or force abstention; it can never create an identity
   edge, merge components, establish protein presence or absence, or infer a missing identity.
9. Preserve every submitted non-secret node, edge, binding, and typed discrepancy needed for
   audit. Canonical ordering changes presentation only; it cannot delete a duplicate, resolve a
   collision, or erase disagreement.
10. Emit no observed peptide, peptide sequence, protein accession, raw copy-number value, raw
    protein abundance, complex-activity score, subtype, proteotype, kinase state, generic fused
    interpretation, treatment recommendation, or clinical decision.

M03-02 is a deterministic, schema-first reconciliation service with append-only input semantics.
Its CN-to-protein check consumes only privacy-minimized, categorical concordance declarations. It
is not an identity solver, database search, peptide-to-protein inference engine, accession resolver,
copy-number regression estimator, activity model, mutable event ledger, laboratory information
system, or clinical decision-support service.

All authorities, review identifiers, reference receipts, and content digests are caller-declared.
Their exact binding makes a result reproducible and tamper-evident under the declared digest rules;
it does not authenticate an issuer, prove source truth, or attest that a laboratory step occurred.
Recovery requires a new governed request that retains the discrepant evidence rather than editing a
prior result. Critical discrepancy, override, claim promotion, novel use, release exception, or
unresolved biological conflict requires external human review.

## Evidence gate

Gate G0 uses exactly eight synthetic, non-clinical scenario groups: a canonical seven-entity chain
and complete artifact DAG; swaps; collision and duplicate retention; cross-patient propagation; a
malformed DAG; upstream/protocol/search-space drift; all five categorical CN-concordance states;
and authorization, privacy, strictness, capacity, ordering, and derived-digest forgery checks.

The executable replay executes public M01-02 first, supplies that exact resolution digest to the
M03-01 identity binding, then executes public M03-01 and binds both exact outputs into M03-02. It
uses no handwritten upstream-result substitute. Every declared case is executed. It checks complete semantic result
equality under irrelevant ordering, consent-first hostile-input behavior, exact typed outcomes,
recursive privacy and ownership boundaries, and rejection of stale derived values. The synthetic
corpus contains only opaque identifiers, categorical control states, and content digests; it has no
observed peptide, protein accession, or raw copy-number measurement.

The representative benchmark evaluates one complete seven-entity chain and artifact DAG through
the public M03-02 operation. Its broad latency ceiling is only a deterministic regression tripwire;
it is not evidence of identity truth, biological validity, copy-number calibration,
transportability, or clinical readiness.

See the [module manifest](M03-02.manifest.md),
[evidence inventory](../evidence/M03-02.md), and
[traceability matrix](../traceability/GLIO-PROTEOGEN-M03-02.csv).
