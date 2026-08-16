# GLIO-PROTEOGEN-M16-01 — upstream contract resolver

M16-01 is a provisional, safety-gated resolver beneath the KINOPHOS object
consumer. It discovers typed upstream candidates, checks locked version/media
compatibility, and emits only a validated upstream bundle or an auditable typed
compatibility report with safe abstention. Its parent target is
`protein_rna_discordance`; it does not emit the parent output.

Authority is the dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
lines 5436–5476. The ABI remains `0.1.0-provisional` pending owner confirmation.
The owner is Platform engineering, safety class S2, gate G0.

## Resolver boundary

- Candidates are opaque artifact references. The resolver never dereferences,
  mutates, relabels, or authenticates caller-declared upstream content.
- Required kinds, contract version, required media type, consent, support, and
  provenance are explicit. Every incompatibility is typed and auditable.
- Missing required kinds, version mismatch, media mismatch, unresolved controls,
  or unsupported evidence produce abstention with human-review acknowledgement.
- Kinase ownership, generic all-omics fusion, treatment recommendation, identity
  inference, consent inference, disagreement erasure, and unsupported-to-negative
  conversion are prohibited.

## Verification

The contract closes unique candidates/kinds, accepted bundle/report correspondence,
typed issue evidence, canonical request/result digests, derived result identifiers,
seven-dimension uncertainty, control provenance, and abstention review semantics.
FastAPI, Typer, and the strict parse-once plugin share one service seam. The
release verifier checks the frozen fixture digest, six-case evaluator, benchmark
budgets, branch coverage, traceability, and wheel/sdist hashes with isolated import.
