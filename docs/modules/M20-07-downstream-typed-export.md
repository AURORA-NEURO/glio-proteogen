# M20-07 downstream typed export

Status: provisional implementation; Computational biology owner review required.

M20-07 is the bounded downstream typed-export boundary beneath the biomarker-
panel protein-subtype surface. It converts caller-declared, documented fields
into a versioned immutable contract object only when ownership, compatibility,
consent, support, provenance, quality, identity lineage, intended use, and
configuration controls are safe. Otherwise it emits a structured abstention;
unsupported material is never converted into a negative claim.

Authority is the permitted dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
slice `GLIO-PROTEOGEN_240_Module_Dossier.md:7140-7180`. The ABI is explicitly
`0.1.0-provisional`; catalogue, endpoint, and media details remain subject to
owner confirmation. The implementation is stacked on finalized M20-06
`d8c253e5` and binds only the declared
`application/vnd.glio-proteogen.m20-06+json` upstream media type.

Safety and closure rules:

- Seven caller-declared controls are checked fail-closed before field
  evaluation: approved configuration, identity lineage, provenance, consent,
  quality, support, and intended use. An export-ready request's granted consent
  reference must be exactly the same decision, state, policy version, and
  evidence as the execution-context consent control; a different granted
  decision is rejected before export. A withheld or otherwise non-granted
  request remains a safe abstention path.
- Export fields have unique IDs and names, explicit type/version/owner/
  documentation/value digest, and unique evidence. Ownership, configuration,
  signature, consent, and support are retained in the immutable object.
- Versioned and strict compatibility may export when all other controls pass;
  review-required compatibility abstains pending confirmation.
- Withheld consent, unsupported/unknown/missing/non-evaluable/prohibited text,
  malformed upstream media, and unsafe controls produce abstention or safe
  validation failure. No identity or consent inference is performed.
- Results retain all seven uncertainty dimensions, provenance, control
  decisions, evidence, limitations, canonical request/result digests, and
  explicit `emits_parent=false` semantics.

The engine, service, strict parse-once plugin, FastAPI adapter, and Typer
adapter share one canonical request path. Replay verification rejects payload,
ownership, and deterministic-result tampering. The evaluator contains one
nominal export and eight adversarial scenarios; the locked benchmark uses
provisional 500 ms mean and 750 ms p95 budgets.

Explicitly out of scope are identity or consent inference, issuer
authentication, raw artifact traversal, kinase analysis, generic all-omics
fusion, treatment recommendations, and biological-truth inference.
