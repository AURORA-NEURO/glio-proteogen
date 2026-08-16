# M15-07: plausibility and negative-control adjudicator

M15-07 is the provisional plausibility and negative-control adjudicator beneath
the longitudinal recurrence proteotype. It evaluates orthogonal evidence, known
controls, direction, conservation, assay physics, and competing mechanisms. It
emits only a plausibility grade or an unresolved-conflict record for the
`complex_activity` parent, with typed uncertainty, support, provenance, evidence,
limitations, and explicit abstention.

## Authority and boundary

The implementation is grounded in `GLIO-PROTEOGEN_240_Module_Dossier.md`,
SHA-256 `0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`,
exact lines 5340–5380. The owner is Quality engineering under S2/G3. The
primary architecture is represented as deterministic provisional metadata for a
Bayesian graph, state-space, mechanistic, or foundation-assisted model with
longitudinal state-space; curated/enrichment/mechanistic and orthogonal-consensus
alternates remain explicit. KINOPHOS kinase ownership, generic all-omics fusion,
direct treatment recommendation, identity or consent inference,
mutation/relabeling/erasure, and unsupported-to-negative conversion are
prohibited.

## Contract and runtime

The request is bound to the provisional M15-06 sensitivity result and carries six
release-blocking plausibility controls plus proteome, transcriptome, and PTM
evidence. Seven upstream authorization controls are checked before strict parsing
or hashing. The runtime deterministically evaluates every declared control as
passed, failed, not-evaluable, or abstained. All failed, unsupported, OOD,
negative-control, prohibited, or unresolved-conflict inputs produce no grade,
preserve the evaluation and conflict record, set review-required support, and
remain explicitly abstained.

Supported adjudication emits a high plausibility grade only when every control
passes and no competing mechanism remains unresolved. Request/result digests bind
canonical content; result IDs derive from the request digest. Replay re-executes
the request and rejects tampered or non-equivalent results. Provenance records all
seven upstream controls, input digests, consent, actor, and generation time. All
seven uncertainty dimensions (measurement, sampling, parameter, model form,
identification, support, transport) remain visible with sensitivity notes.

## Interfaces and evidence

The strict plugin uses an issued validate-then-run capability token. FastAPI and
Typer share the typed service and canonical JSON representation, enforce strict
content types and duplicate-key rejection, sanitize errors, and prevent CLI
output overwrite. The evaluator contains nine locked cases covering positive
control adjudication, negative-control and unsupported abstention, visible
conflict, prohibited boundary, replay/tamper, authorization, deterministic
reconstruction, and complete uncertainty/provenance.

The final scoped gate passed 27 focused tests, Ruff, strict MyPy across 13
M15-07 source/eval/tool files, and compileall. Branch-enabled coverage is 96.50%
(493 statements, 480 covered; 78 branches, 71 covered; fail-under 95). Ten
benchmark iterations measured 1,625,840 ns mean, 1,496,700 ns median, and
1,764,200 ns p95 against provisional 2e9/3e9 ns budgets. Release evidence,
traceability, package hashes, and the tamper-checking verifier are under
`release-evidence/m15_07/`.
