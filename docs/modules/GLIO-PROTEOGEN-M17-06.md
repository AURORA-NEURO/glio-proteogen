# GLIO-PROTEOGEN-M17-06 — Reviewer discrepancy and adjudication queue

## Authority and scope

M17-06 is traceable to dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact lines
`6016-6056`. The ABI is `0.1.0-provisional`; the dossier is behavioral authority only
until Clinical science confirms the endpoint and media catalogue.

The module owns structured disagreement, reason codes, blinded reviewer assignment,
escalation, resolution, and immutable audit history beneath C17 Metabolomic/lipidomic
integration. It emits only a versioned variant-peptide adjudication record. It does not
own KINOPHOS kinase state, generic all-omics fusion, direct treatment recommendation,
identity or consent inference, upstream evidence mutation, relabeling, erasure, or an
unsupported negative finding.

## Contract

The request is bound to the caller-declared M17-05 workspace media type and carries
mass-spectrometry, genome/transcriptome, PTM, configuration, lineage, provenance, consent,
quality, support, intended-use, discrepancy, and reviewer-assignment references. Every
queue entry requires exactly one opaque, blinded assignment. Critical entries promoted to
a recorded result require a final accept/reject decision; unresolved, deferred, escalated,
or unsupported material remains abstained.

The output has two mutually exclusive states:

- `recorded`: a supported, locked, resolved `AdjudicationRecord` containing every queue
  entry, all assignments, ordered contiguous audit events, resolution summary, evidence,
  and a content digest;
- `abstained`: no record, explicit reason, `review_required` or `unsupported` support
  status, findings, uncertainty, provenance, evidence, and limitations.

Canonical request and result projections bind replay to exact bytes. The result digest,
request digest, result identity, queue membership, assignment coverage, and immutable
history are revalidated before release or replay.

## Runtime controls

Seven caller-declared controls are required and recorded: approved configuration, identity
lineage, provenance, consent, quality, support, and intended use. The runtime fails closed
when controls are missing or not accepted, when boundary markers indicate unsupported or
prohibited scope, or when the queue cannot be safely promoted. It reports measurement,
sampling, parameter, model-form, identification, support, and transport uncertainty even
for abstained results. Reviewer tokens remain opaque and are never inferred from identity.

## Interfaces and evidence

The standalone adapter exposes strict FastAPI schema/adjudicate/verify routes and Typer
export-schema/adjudicate/verify commands. The plugin parses JSON once, issues an opaque
validated token, and refuses forged tokens. Errors are sanitized and CLI output never
overwrites an existing result.

The frozen evaluator covers resolved recording, unresolved review, escalation, unsupported
and prohibited abstention, replay/tamper rejection, authorization, deterministic
reconstruction, uncertainty/provenance completeness, and complete blinded assignment.
All evidence is engineering-provisional and requires human review before any clinical use.
