# GLIO-PROTEOGEN-M16-04 — intended-use adapter

M16-04 is a provisional, safety-gated adapter beneath the KINOPHOS object
consumer. It converts an opaque research result into a registered,
intended-use-specific object with an explicit audience, evidence tier, claim
ceiling, display semantic, limitations, and auditable policy decision. Its
parent target is `protein_rna_discordance`; it does not emit the parent output.

Authority is the dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
lines 5568–5611. The ABI remains `0.1.0-provisional` pending owner
confirmation. The owner is Bioinformatics, safety class S2, gate G3.

## Intended-use boundary

- Every adapted object binds a registered policy, audience, minimum evidence
  tier, maximum claim ceiling, permitted/prohibited claims, and display
  semantic.
- The adapter references the M16-01 upstream result by immutable artifact
  digest. It never dereferences, mutates, relabels, or authenticates external
  content.
- Exploratory evidence is visible only as `qualified`; hidden or abstaining
  policies, prohibited claims, missing controls, and unresolved policy states
  produce explicit abstention with human-review acknowledgement.
- Kinase ownership, generic all-omics fusion, treatment recommendation,
  identity inference, consent inference, disagreement erasure, and
  unsupported-to-negative conversion are prohibited.

## Verification

The contract closes policy claim uniqueness/disjointness, clinical and evidence
compatibility, canonical request/result digests, seven-dimension uncertainty,
control provenance, typed findings, and abstention review semantics. FastAPI,
Typer, and the strict parse-once plugin share one service seam. The release
verifier checks the frozen six-case fixture digest, evaluator, benchmark
budgets, branch coverage, traceability, and wheel/sdist hashes with isolated
import.

