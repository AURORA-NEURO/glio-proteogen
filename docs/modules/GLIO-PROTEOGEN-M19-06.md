# GLIO-PROTEOGEN-M19-06 — reviewer discrepancy and adjudication queue

M19-06 provides a bounded, deterministic adjudication queue for structured
disagreement beneath the proteotype target. It preserves reviewer decisions,
reason codes, escalation, resolution, and immutable audit history. It does not
infer biological truth or convert missing/unsupported material into a negative.
The ABI is provisional because the dossier is behavioral authority rather than
a frozen endpoint catalogue.

## Authority and boundary

| Property | Binding |
| --- | --- |
| Dossier SHA-256 | `0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181` |
| Exact slice | `GLIO-PROTEOGEN_240_Module_Dossier.md:6736-6776` |
| Owner / safety / gate | Platform engineering / S2 / G4 |
| Parent | `proteotype` only; `emits_parent=false` |
| Operation / version | `adjudicate_proteotype_discrepancy_queue` / `0.1.0-provisional` |
| Upstream boundary | Caller-declared M19-05 media reference; content is not dereferenced |
| Output ceiling | Structured review record, typed findings, support, uncertainty, provenance, evidence, or abstention |

M19-06 does not perform KINOPHOS kinase work, generic all-omics fusion,
treatment recommendation, identity or consent inference, mutation inference,
or external-content traversal. It preserves disagreement and never emits a
negative finding solely because evidence is missing or unsupported.

## Contract and runtime closure

- Strict contracts close queue-entry, assignment, audit-event, finding,
  configuration, request, record, and result identities.
- Seven caller-declared controls are checked before upstream material is
  considered. Every decision retains control, support, provenance, evidence,
  and seven-dimensional uncertainty metadata.
- Critical discrepancies require two distinct blinded reviewers. Assignment
  IDs, discrepancy IDs, audit IDs, and sequence numbers are unique; history is
  contiguous, append-only, and hash chained.
- Only a resolved queue with final accept/reject decisions can emit a record.
  Queued, in-review, escalated, not-evaluable, unsupported, or failed control
  states abstain safely without a record.
- Request and result digests are canonical and replay verification rejects
  payload, result, or audit-chain tampering.

## Interfaces and evidence

FastAPI exposes schema, adjudicate, and verify routes. Typer exposes
`export-schema`, `adjudicate`, and `verify`; all adapters parse strict JSON once,
sanitize validation/authentication errors, and refuse overwriting CLI output.
The plugin descriptor carries the same Platform engineering/S2/G4 authority
ceiling.

The frozen evaluator executes eight declared scenarios and seven adversarial
cases: resolved recording, unresolved and not-evaluable abstention, consent
preflight, upstream media rejection, replay tamper, audit-chain tamper, and
duplicate discrepancy rejection. The benchmark is a deterministic software
regression tripwire, not scientific validation.
