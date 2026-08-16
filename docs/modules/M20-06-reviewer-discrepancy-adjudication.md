# M20-06 reviewer discrepancy adjudication

Status: provisional implementation; Scientific engineering owner review required.

M20-06 is the bounded reviewer-discrepancy and adjudication queue beneath the
biomarker-panel protein-subtype surface. It accepts a caller-declared M20-05
workflow result, preserves discrepant entries and blinded assignments, records
an immutable audit history, and emits either a resolved human-review record or
a safe abstention. The module never converts unsupported, unresolved, or
non-evaluable evidence into a negative biological claim.

Authority is the permitted dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
slice `GLIO-PROTEOGEN_240_Module_Dossier.md:7096-7136`. The ABI is explicitly
`0.1.0-provisional`; catalogue, endpoint, and media details remain subject to
review. The implementation is stacked on the finalized M20-05 head
`d14cdca0` (itself based on M20-04 `c59e5217`) and binds only the declared
`application/vnd.glio-proteogen.m20-05+json` media type.

Safety and closure rules:

- Seven caller-declared controls are checked fail-closed before queue
  traversal: approved configuration, identity lineage, provenance, consent,
  quality, support, and intended use.
- Every discrepancy is retained with a reason, severity, description, evidence,
  and explicit state. Reviewer assignments are blinded, unique by discrepancy
  and reviewer token, and linked to the queue.
- Resolved records require every entry to be resolved, only final accept/reject
  decisions, a non-empty resolution summary, and contiguous immutable audit
  history. Escalated/non-evaluable material cannot claim final resolution.
- Missing assignment, unresolved/deferred, critical, unsupported, malformed, or
  non-evaluable input produces an abstained result with findings and no record.
- Results retain all seven uncertainty dimensions, control decisions,
  provenance, evidence, limitations, replay digests, and a mandatory human
  review flag. `emits_parent` is permanently false.

The engine, service, strict parse-once plugin, FastAPI adapter, and Typer
adapter share one canonical request path. Request/result digests and replay
verification reject payload or audit-history tampering. The evaluator covers
one nominal resolution and eight adversarial scenarios; the locked benchmark
uses provisional 500 ms mean and 750 ms p95 budgets.

Explicitly out of scope are identity inference or authentication, consent
inference, treatment recommendations, kinase analysis, generic all-omics
fusion, raw artifact traversal, and claims about biological truth.
