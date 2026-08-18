# GLIO-PROTEOGEN-M13-01 — biological hypothesis registry

## Authority and status

This implementation is traced to dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, lines
4356–4399. The dossier describes the M13-01 responsibility beneath the
proteotype channel, with Quality engineering ownership, S2 safety, and G0
gate. The endpoint and media type remain provisional (`0.1.0-provisional`);
owner confirmation is still required before an ABI can be frozen.

## Behavior

M13-01 accepts caller-declared hypotheses with mechanism classes, target IDs,
competing explanations, evidence tiers, falsification rules, prohibited
interpretations, and immutable source-artifact references. It evaluates only a
small closed vocabulary (`supported`/`true` and `passed`/`pass`) and abstains
for refuted, missing, unsupported, or unknown outcomes. Every result binds the
exact request digest, deterministic result ID and result digest, seven-axis
uncertainty profile, seven upstream control decisions, provenance and evidence.

The runtime never traverses source-artifact payloads, mutates upstream
evidence, infers identity or consent, or converts unsupported evidence into a
negative finding. Kinase activity remains KINOPHOS-owned; generic all-omics
fusion and direct treatment recommendations are prohibited. Abstention emits
no registry and requires human review acknowledgement.

## Verification

- 25 focused contract/runtime/interface/evaluator/release tests pass.
- Ruff and strict MyPy pass for 14 scoped source/evaluation/test files.
- Branch-enabled scoped coverage: 97% (510 statements, 74 branch arcs).
- Seven fixture scenarios pass, including supported, refuted, unknown,
  failed/unknown falsification, multi-hypothesis and denied-control paths.
- Two-iteration benchmark passes provisional 2 s mean / 3 s p95 budgets.
- Replay verification rejects digest, result-ID, evidence, evaluation and
  nested-registry tampering.
- FastAPI and Typer adapters share strict parse-once canonical validation and
  sanitized error behavior.

## Recovery and release

The operation is deterministic for the same validated request. A result can be
verified with replay enabled, while replay-disabled digest verification remains
available for an independently transported result. The release verifier binds
fixture IDs/digest, benchmark budgets, coverage threshold, package hashes,
member counts and isolated-wheel imports.
