# GLIO-PROTEOGEN-M14-08 — mechanism evidence dossier

M14-08 publishes a deterministic, review-ready mechanism evidence dossier beneath the
microenvironment protein deconvolution family. It consumes caller-declared M14-07 mechanism
references and produces a reconstructable dossier for the `protein_subtype` parent. The
implementation is deliberately provisional (`0.1.0-provisional`): it binds the current
authority slice without claiming that a production ABI, model catalogue, endpoint, or media
type has been frozen.

## Authority and boundary

The implementation is derived from the permitted dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact lines 5024–5064.
The dossier names Bayesian/state-space/mechanistic/foundation methods with a network-factor
hybrid, curated/enrichment/mechanistic and Bayesian-model-averaging alternatives, and an
orthogonal-consensus fallback. Gate G3 permits only the closed deterministic evidence-graph
projection installed here. The runtime does not fit models, dereference scientific content,
infer identity or consent, or emit a treatment recommendation.

The parent target remains `protein_subtype`; `emits_parent` is always false. The result is a
quality-controlled evidence record, not a new protein subtype, kinase activity call, all-omics
fusion, treatment decision, or authenticated scientific conclusion. Caller-declared references
are provenance inputs, not credentials: their digests make replay deterministic but do not
authenticate an issuer, assay, reviewer, laboratory, or biological truth.

## Contract and replay closure

`PublishProteinSubtypeMechanismDossierRequest` is strict and frozen. It binds one request ID,
the seven execution controls, the provisional M14-07 media type, a locked configuration, a
dossier, and at least one source artifact. A dossier contains unique links, claims, and
validation routes. Every claim must point to available links and carry both evidence and
counter-evidence. A supported link must carry evidence; missing, unresolved, or abstained
links cannot silently become support.

The result binds the canonical request digest and derives its result ID from that digest.
Result evidence is restricted to evidence-role references. A review-ready result must contain a
supported dossier; an abstained result must contain no dossier, an explicit reason, a safe
unsupported/review-required status, and human-review acknowledgement. Canonical request and
result bytes are replayed before publication and verified again by the service and adapter.
Tampered digests, identifiers, support states, evidence roles, or dossier presence are rejected.

## Runtime decision policy

The engine executes the following ordered policy:

1. Read the seven control decisions using the authorization firewall. Rejected, unresolved,
   withheld, or otherwise unsafe controls fail before request traversal.
2. Require a supported M14-07 reference and a closed method from the provisional catalogue:
   `evidence_graph`, `curated_rule`, `mechanistic_baseline`, `bayesian_graph`, or
   `orthogonal_consensus`.
3. Require every validation route to be `complete`, every link to be supported or limited, and
   every claim to retain links, evidence, and counter-evidence.
4. Emit a supported review-ready dossier with the seven uncertainty dimensions, seven control
   provenance decisions, explicit limitations, and a claim ceiling; otherwise abstain safely.

Abstention is used for required validation, unresolved/abstained/conflicted evidence, unknown
methods, upstream mismatches, and authorization failure. No negative mechanism is inferred from
missing evidence. A human review acknowledgement remains required for every abstention.

## Interfaces

The strict parse-once plugin binds one authorization token to one typed request and exposes
`infer` and `verify`. FastAPI exposes metadata-only schema retrieval at
`GET /v1/m14-08/schema/{name}`, dossier publication at
`POST /v1/modules/M14-08/dossier`, and replay verification at
`POST /v1/modules/M14-08/verify`. Typer exposes `export-schema`, `infer`, and `verify` with
duplicate-key rejection, sanitized errors, strict JSON, and no-overwrite output semantics.
All interfaces route through the same service and therefore have canonical parity.

## Evaluation, safety, and release gate

The frozen fixture contains seven unique scenarios: review-ready publication, counter-evidence
chain, required validation abstention, unresolved-link abstention, unsupported-method
abstention, replay/tamper detection, and authorization rejection. The evaluator requires exact
declared-versus-executed case closure. The adversarial matrix additionally covers duplicate
links/claims/routes, unavailable claim links, upstream media tampering, result closure, hostile
object traversal, plugin token binding, API/CLI error paths, duplicate JSON, and canonical
ordering.

The scoped release gate requires Ruff, strict MyPy, compileall, focused tests, branch coverage
at least 95%, evaluator closure, benchmark budgets, wheel/sdist construction, and an isolated
wheel import. The representative benchmark performs ten public calls after one untimed warmup;
its budgets are 2,000,000,000 ns mean and 3,000,000,000 ns nearest-rank p95. These are software
regression budgets, not claims about scientific validity, calibration, transportability, or
clinical utility.

See the [evidence inventory](../evidence/M14-08.md) and
[traceability matrix](../traceability/GLIO-PROTEOGEN-M14-08.csv).
