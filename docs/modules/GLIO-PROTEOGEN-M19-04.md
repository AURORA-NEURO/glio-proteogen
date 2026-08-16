# GLIO-PROTEOGEN-M19-04 - intended-use adapter

M19-04 adapts one immutable M19-03 proteotype evidence result into a bounded,
caller-declared intended-use object beneath Immunopeptidomic evidence. The implementation is
provisional because the dossier provides a behavioural brief rather than a frozen ABI. It
therefore exposes strict schemas, deterministic policy decisions, replay digests, explicit
support, seven uncertainty dimensions, provenance, evidence, limitations, and safe abstention.

## Authority and ceiling

| Property | Locked value |
| --- | --- |
| Dossier | `GLIO-PROTEOGEN_240_Module_Dossier.md` SHA-256 `0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181` |
| Slice | lines 6648-6688 |
| Module / operation | `GLIO-PROTEOGEN-M19-04` / `adapt_proteotype_intended_use` |
| Parent context | `proteotype` only; the adapter never emits the parent |
| Owner / gate | Clinical science / S2 / G3 |
| Input | Exact M19-03 media type plus caller-declared source artifacts and registration |
| Output | Bounded intended-use object or typed abstention; no biological inference |
| ABI state | `0.1.0-provisional`, dossier-behavioural-brief-only |

The adapter never infers identity or consent, authenticates issuers, dereferences external
content, mutates or relabels upstream results, erases disagreement, promotes unsupported
evidence, emits KINOPHOS kinase activity, performs all-omics fusion, or recommends treatment.
Clinical/release use remains visibly review-gated. Critical discrepancy, support override, OOD
state, claim promotion, release exception, or unresolved conflict remains external review work.

## Locked behavior

1. Require all seven caller-declared controls—approved configuration, identity lineage,
   provenance, consent, quality, support, and intended use—before typed request traversal.
   Denied, missing, or malformed controls fail closed.
2. Parse strictly once through the M19-04 request model. Unknown fields, coercion, duplicate
   source IDs/digests, wrong upstream media, and missing exact upstream inclusion reject.
3. Require unique intended-use registration, evidence tier, claim ceiling, prohibited
   interpretations, and ordered display sections. Uniqueness is structural, not a best effort.
4. Permit only the vocabulary `research`, `internal_validation`, `clinical_review`, and
   `release_review`; enforce evidence tiers 1, 2, 3, and 4 respectively.
5. Require display disclosure of support, uncertainty, provenance, evidence, and limitations.
   Incomplete disclosure abstains rather than silently hiding limitations.
6. Treat treatment, therapeutic, recommendation, kinase, all-omics, identity-inference, and
   direct-treatment terms in the requested maximum claim as blocked policy claims.
7. Emit a supported bounded object only for an allowed or review-required policy decision. A
   blocked policy emits no object, a typed abstention reason, unsupported support status, unique
   findings, and human-review-required state.
8. Clinical and release decisions are adapted only with `review_required`; they never appear as
   unrestricted research output.
9. Emit all seven uncertainty dimensions as `not_estimable`; policy adaptation is not a biology
   estimator and makes no calibration, probability, or transport claim.
10. Preserve exact source and registration evidence, seven control decisions, provenance,
    limitations, parent ceiling, and false authority flags in every result.
11. Derive request digest, result identifier, result payload digest, activity identifier, and
    object identifier deterministically from canonical content. Replay revalidates the complete
    result and rejects identifier, request, payload, and tamper changes.
12. Keep the runtime stateless. The service and strict plugin are thin seams over the same
    engine; FastAPI, Typer, and plugin outputs are canonical-parity projections.
13. Export strict JSON Schema 2020-12 contracts for request, output, registration, claim ceiling,
    display semantics, policy decision, intended-use object, and finding.
14. Benchmark only the public adapter call after one untimed warm-up. The provisional software
    budgets are mean <=500 ms and p95 <=750 ms; these are not scientific validation.

## Interfaces and recovery

The API exposes schema GET `/v1/contracts/M19-04/{name}/schema`, adaptation POST
`/v1/modules/M19-04/adapt`, and replay POST `/v1/modules/M19-04/verify`. Typer exposes
`m1904-intended-use export-schema`, `adapt`, and `verify`. Errors are sanitized and unauthorized
or tampered requests never leak tracebacks. Recovery is append-only: retain the immutable request,
result, evidence, and review record; submit a new request naming any superseded digest; publish to
a new path; and require fresh external review.

See the [manifest](M19-04.manifest.md), [evidence inventory](../evidence/M19-04.md), and
[traceability matrix](../traceability/GLIO-PROTEOGEN-M19-04.csv).
