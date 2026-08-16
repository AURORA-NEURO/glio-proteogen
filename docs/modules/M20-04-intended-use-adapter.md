# M20-04 intended-use adapter

Status: provisional implementation; Data engineering owner review required.

M20-04 is a deterministic, replay-verifiable adapter beneath protein-subtype
translation. It binds one caller-declared M20-03 integrated-evidence artifact to a
locked intended-use registration: audience, evidence tier, claim ceiling, display
semantics, support, uncertainty, evidence and limitations remain explicit.

Authority: dossier SHA-256 `0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`,
lines `7008-7048`. The implementation is explicitly `0.1.0-provisional`; no frozen
ABI, catalogue, endpoint or media type is claimed beyond the current behavioral
contract. The exact upstream binding is
`application/vnd.glio-proteogen.m20-03+json`; the branch also carries finalized
M20-02 alignment evidence and M20-03 fusion as explicit dependency merges.

Safety boundaries:

- No raw artifact traversal, identity or consent inference, kinase activity,
  all-omics fusion, treatment recommendation, diagnosis or unsupported-to-negative
  conversion.
- Prohibited claims, insufficient review evidence, incomplete display semantics,
  unsafe controls and invalid upstream media fail closed with explicit findings and
  human review; abstention never becomes a negative biological conclusion.
- Seven caller-declared controls are checked before policy or source traversal.
- All seven uncertainty dimensions are present as explicit not-estimable states;
  provenance records source digests and every control decision.

The service, plugin, FastAPI adapter and Typer adapter share one strict parse-once
request path and canonical replay digest. The evaluator executes eight scenarios and
eight adversarial cases; benchmark budgets are provisional 500 ms mean and 750 ms
p95.
