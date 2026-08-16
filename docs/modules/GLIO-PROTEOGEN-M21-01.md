# GLIO-PROTEOGEN-M21-01 — Reference truth and benchmark curator

## Authority and scope

M21-01 is traceable to dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
authority slice `7185–7228` in the permitted repository dossier mirror. The
ABI remains `0.1.0-provisional`; this implementation records behavioral
requirements only and does not promote an endpoint catalogue or media type to
an externally frozen standard.

The module is owned by Quality engineering beneath Reference material/spike-ins,
at S3/G0. It owns caller-declared reference data, positive/negative controls,
endpoint definitions, provenance, inclusion and leakage audits, challenge sets,
independent adjudication, and immutable lock procedures. It emits only a
versioned benchmark/reference-truth package supporting the complex-activity
parent boundary; it does not emit a complex-activity estimate.

Upstream M20-08, M16-08, and M06-08 are represented only through the required
typed seven-control context. No unfrozen upstream runtime ABI is invented or
traversed. Downstream M21-02 and M21-03 may consume the provisional media type
after their own authority and compatibility checks.

The module does not authenticate issuers or review authority, mutate or relabel
upstream evidence, infer identity or consent, perform generic all-omics fusion,
own KINOPHOS kinase state, recommend treatment, or convert unsupported/missing
evidence into a negative finding.

## Contract closure

The request is strict, immutable, size-bounded, and bound to an execution
context with matching request identity. Reference/control partitions are
globally unique and kind-closed. Every item has inclusion and leakage-audit
coverage plus a distinct adjudication record. Challenge identifiers exactly
match challenge-set entries. Locked packages require a locked configuration,
locked/rejected adjudications, explicit disagreement for rejection, matching
package/configuration versions, and a canonical lock digest that excludes only
the digest field itself.

The result deterministically derives its identifier from the canonical request
digest. Curated results must carry a supported locked package exactly equal to
the request. Abstentions carry no package, a review-required support decision,
an explicit reason, findings, seven uncertainty dimensions, provenance,
limitations, and human-review escalation. Result and replay digests reject
tampering.

## Runtime, interfaces, and evidence

Runtime preflight requires accepted configuration, resolved identity lineage,
accepted provenance, granted consent, accepted quality, accepted support, and
accepted intended use. The strict parse-once plugin, FastAPI adapter, and Typer
adapter expose schema, validate, curate, and verify operations. API errors are
sanitized; CLI outputs refuse overwrite; invalid execution tokens cannot bypass
validation.

The frozen evaluator covers supported curation, locked package replay, pending
adjudication abstention, denied-control fail-closed behavior, deterministic
reconstruction, and replay verification. The adversarial suite covers malformed
control mappings, request/context identity mismatch, challenge partition drift,
lock-digest tampering, result tampering, plugin misuse, API sanitization, and
CLI abstention behavior. All implementation evidence remains provisional and
requires owner review before any scientific or clinical promotion.
