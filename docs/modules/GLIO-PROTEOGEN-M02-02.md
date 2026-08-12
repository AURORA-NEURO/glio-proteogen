# M02-02: identity and lineage reconciliation

M02-02 audits peptide-identification artifact bindings against an immutable identity resolution
already issued upstream. It checks whether opaque artifact assignments remain bound to the
declared entity component, subject component, scoped token, and content digest. It detects
swaps, same-scope token collisions, duplicate content assignments, and cross-patient links. It
does not merge entities, infer identity, or rerun the upstream identity solver.

## Audit boundary

1. Require consent and accepted configuration, provenance, quality, support, and intended-use
   controls before traversing artifact bindings.
2. Bind the request to one exact upstream identity-resolution digest and one versioned policy.
3. Reuse the upstream graph's opaque entity and subject component identifiers. Never accept or
   return names, medical-record identifiers, accession labels, raw token values, or measurements.
4. Compare observed subject components with the upstream component set. A mismatch is a swap;
   more than one subject component on a run or derived object is a cross-patient link.
5. Compare opaque token digests only within the same declared scope. The same digest in different
   scopes is not a collision.
6. Detect identical artifact-content digests assigned through distinct bindings without
   deciding which source is authoritative or deleting either assignment.
7. Preserve unresolved and unsupported states as abstentions. They are never converted into a
   negative identity finding or a guessed link.
8. Return only a privacy-minimized binding evaluation and a canonical presentation of the
   semantically unchanged upstream lineage graph.

The implementation is a stateless deterministic audit. It has no database, event ledger,
identity model, mixed-effects model, matching heuristic, raw-identifier store, or reviewer UI.

## Evidence gate

Gate G0 uses eight synthetic, non-clinical cases:

- a conformant set of already-resolved run and derived-object bindings;
- declared-versus-observed subject-component swap detection;
- same-scope opaque-token collision detection, with a different-scope control;
- duplicate content assignment across distinct bindings;
- a run bound across patient components;
- an explicitly unresolved binding that abstains;
- an explicitly unsupported binding that abstains; and
- a paired upstream-unresolved result and consent-denied preflight check.

The executable replay also checks order-independent full-result equality, digest stability, and a
closed privacy boundary. One broad batch benchmark is a representative latency regression
tripwire rather than an asymptotic or scientific-performance claim.

These checks establish deterministic behavior for one synthetic binding-audit profile. They do
not establish real-world identity correctness, specimen provenance, fraud detection, clinical
readiness, protein subtype, biological validity, kinase activity, treatment suitability, or
cross-omics interpretation.

See the [module manifest](M02-02.manifest.md),
[evidence inventory](../evidence/M02-02.md), and
[traceability matrix](../traceability/GLIO-PROTEOGEN-M02-02.csv).
