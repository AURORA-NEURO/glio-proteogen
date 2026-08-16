# M15-01: biological hypothesis registry

M15-01 is the provisional biological hypothesis and falsification registry beneath
the longitudinal recurrence proteotype. It accepts caller-declared proteome,
genome/transcriptome, PTM, and seven upstream control objects, and emits only a
versioned registry for the `complex_activity` parent. The ABI remains provisional
(`0.1.0-provisional`) pending owner confirmation.

## Authority and boundary

The implementation is grounded in `GLIO-PROTEOGEN_240_Module_Dossier.md`, SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact lines
5076–5116. The owner is Data engineering under S2/G0. KINOPHOS kinase-state
ownership, generic all-omics fusion, direct treatment recommendation, identity or
consent inference, upstream mutation/relabeling/erasure, and unsupported-to-negative
conversion are outside this module.

## Contract and runtime

Each hypothesis requires a mechanism class, target IDs, competing explanations,
falsification rules, evidence tiers, prohibited interpretations, and source
evidence. Request and result digests bind canonical content; result IDs derive from
the request digest. Every hypothesis and falsification rule receives exactly one
evaluation. A supported result requires all evaluations and rules to pass, a locked
registry, supported support status, and no review flag. Otherwise the runtime emits
an explicit review-required abstention with findings, limitations, typed uncertainty,
and provenance.

Seven upstream controls are checked before parsing or hashing. Malformed or hostile
opaque objects fail closed. The uncertainty profile exposes measurement, sampling,
parameter, model-form, identification, support, and transport dimensions, with
sensitivity notes. Replay re-executes the exact request and rejects tampered results.

## Interfaces and evidence

The strict plugin uses an issued validate-then-run capability token. FastAPI and
Typer adapters share the service and canonical JSON representation, enforce strict
content types and duplicate-key rejection, sanitize validation errors, and prevent
CLI output overwrite. The nine-case evaluator covers supported registration,
unsupported tier, failed falsification, prohibited statement, conflicted hypothesis,
replay/tamper, authorization, deterministic reconstruction, and complete
provenance/uncertainty.

The final scoped gate passed 34 focused tests, Ruff, strict MyPy for the new source,
and 96.33% branch-enabled scoped coverage (550 statements, 535 covered; 104
branches, 95 covered; fail-under 95). Ten benchmark iterations measured 1,405,910 ns
mean, 1,322,500 ns median, and 1,376,200 ns p95 against provisional 2e9/3e9 ns
budgets. Release evidence, traceability, package hashes, and the tamper-checking
verifier are under `release-evidence/m15_01/`.
