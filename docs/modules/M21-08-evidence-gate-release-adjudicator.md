# M21-08 evidence gate and release adjudicator

Status: provisional implementation; ML engineering owner confirmation remains
required before any promotion decision.

M21-08 is a deterministic evidence gate beneath the complex-activity parent.
It adjudicates caller-declared requirements, locked benchmark outcomes,
residual risks, approvals, post-release obligations, and traceable evidence.
It emits a typed gate status and, only when every declared closure condition
passes, a signed release record. It never emits a complex-activity estimate,
kinase activity, generic all-omics fusion, treatment recommendation, identity
inference, or consent inference.

Authority is dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
slice `GLIO-PROTEOGEN_240_Module_Dossier.md:7544-7584`. ABI status remains
`0.1.0-provisional`; no frozen catalogue or endpoint is claimed.

The request binds the exact M21-07 input media
`application/vnd.glio-proteogen.m21-07+json` and retains at least one M21-06
robustness artifact with media
`application/vnd.glio-proteogen.m21-06+json`. This is an evidence/media
boundary only: M21-08 imports neither upstream runtime. Source artifacts and
evidence references are unique and digest-bound.

Seven accepted controls are required before evidence traversal: approved
configuration, identity lineage, provenance, consent, quality, support, and
intended use. Denied, malformed, or incomplete controls fail closed. Every
result carries seven explicit `NOT_ESTIMABLE` uncertainty dimensions,
provenance with all control decisions, evidence, limitations, and human-review
semantics. Failed requirements, failed benchmarks, open critical risks, or
non-approve decisions produce safe abstention with findings and no release
record.

The engine, service, opaque strict-parse-once plugin, FastAPI adapter, and
Typer adapter share canonical request/result digests and replay/tamper
verification. The frozen evaluator covers ten cases; adversarial coverage
exercises media boundaries, malformed JSON, control denial, abstention,
tampering, CLI no-overwrite, and API/CLI/plugin parity.
