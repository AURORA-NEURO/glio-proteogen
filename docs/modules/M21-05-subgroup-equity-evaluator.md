# M21-05 subgroup equity evaluator

Status: provisional implementation; Scientific engineering owner review
required.

M21-05 is the bounded subgroup-equity evaluation boundary beneath the complex
activity surface. It evaluates caller-declared subgroup performance,
calibration, coverage, and equity material only when the locked configuration
and seven upstream controls are accepted. Unsupported, limited, non-evaluable,
or unsafe material produces an explicit abstention; it is never converted into
a negative biological claim.

Authority is the permitted dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
slice `GLIO-PROTEOGEN_240_Module_Dossier.md:7412-7452`. The ABI is explicitly
`0.1.0-provisional`; catalogue, endpoint, and media details remain subject to
owner confirmation. The implementation is stacked on finalized M21-03
`addb04ec` and binds only the declared
`application/vnd.glio-proteogen.m21-04+json` upstream media type. M21-04 has no
frozen runtime ABI in this lane and is not imported.

Safety and closure rules:

- Seven caller-declared controls are checked fail-closed before subgroup
  traversal: approved configuration, identity lineage, provenance, consent,
  quality, support, and intended use.
- Performance, calibration, and coverage strata must align exactly across all
  eight required dimensions. Numeric fields are finite and bounded; safety
  floors, nominal coverage, canonical fractions, unique IDs, and evidence
  closure are enforced.
- Unsupported/limited coverage, equity floor breaches, rare-context gaps,
  calibration failure, denied controls, malformed upstream media, and replay
  tampering produce safe abstention or sanitized validation failure.
- Results retain seven uncertainty dimensions, provenance, control decisions,
  evidence, limitations, canonical request/result digests, and explicit
  `emits_parent=false` semantics. No parent complex-activity result is emitted.

The engine, service, strict parse-once plugin, FastAPI adapter, and Typer
adapter share one canonical request path. The evaluator contains one nominal
case and eight adversarial cases; the locked benchmark uses provisional
500,000,000 ns mean and 750,000,000 ns p95 budgets.

Explicitly out of scope are identity or consent inference, issuer
authentication, raw artifact traversal, kinase analysis, generic all-omics
fusion, treatment recommendations, and unsupported-to-negative inference.
