# M24-07 human-factors and operational evaluator

Status: provisional implementation; Clinical science owner review required.

M24-07 is the human-factors and operational evaluator beneath the dossier's
Batch/missing-protein sensitivity component. It measures reviewer comprehension,
automation bias, throughput, latency, downtime, recovery and fallback. It emits
only a caller-declared human-factors and operational validation report with
support, uncertainty, provenance, evidence, limitations and explicit abstention.

Authority is the permitted dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
slice `GLIO-PROTEOGEN_240_Module_Dossier.md:8580-8620`. The ABI remains
`0.1.0-provisional`; no frozen endpoint, catalogue or production media type is
claimed. M24-06 is an unpublished caller-declared media producer. M24-07 binds
its declared `application/vnd.glio-proteogen.m24-06+json` media type only and
imports no M24-06 runtime service or implementation.

Safety and lifecycle closure:

- Locked configuration requires all seven operational dimensions, metric and
  fallback evidence, explicit tolerances, sample sizes, and bounded recovery.
- Seven caller-declared controls are checked fail-closed before traversing
  operational content. Any failed/not-evaluable metric or unavailable fallback
  produces review-required abstention without a report.
- Replay verifies canonical request digest, deterministic result identity,
  result payload digest, provenance controls, evidence binding and finding
  uniqueness. All seven uncertainty dimensions are explicit `not_estimable`.
- FastAPI, Typer and plugin adapters use strict parse-once boundaries, sanitize
  validation failures, preserve canonical bytes, refuse overwrite, and expose
  nonzero abstention behavior.
- KINOPHOS kinase-state ownership, generic all-omics fusion, treatment
  recommendation, identity/consent inference, unsupported-to-negative
  conversion, upstream mutation and biomarker-panel conclusions are prohibited.

Evidence is caller-declared and not issuer-authenticated. This module supports
human review and operational validation; it does not establish clinical efficacy,
clinical utility, or a production intended-use claim.
