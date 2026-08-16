# GLIO-PROTEOGEN-M16-07 — downstream typed export

Status: provisional implementation, release-evidence complete, ABI not frozen.

## Authority and ownership

- Dossier: `GLIO-PROTEOGEN_240_Module_Dossier.md`
- Authority SHA-256: `0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`
- Exact authority slice: lines `5700-5740`
- Owner: Clinical science / S2 / G3
- Parent target: `protein_rna_discordance`
- Consumer boundary: downstream typed export beneath the KINOPHOS object consumer
- ABI: `0.1.0-provisional`; the dossier does not freeze a public endpoint catalogue or media registry

The implementation is intentionally caller-declared and versioned. It turns a validated,
consent-aware, support-aware request into an immutable signed downstream contract only when
ownership, compatibility, media type, support, and all seven upstream control decisions pass.
The signed contract is not a kinase inference, all-omics fusion, treatment recommendation,
identity inference, consent decision, mutation/relabel operation, or unsupported negative claim.

## Contract boundary

The request binds the provisional M16-04 intended-use result and declares:

1. a request and execution context;
2. the consumer policy, allowed field owner, required media type, and configuration signature;
3. one or more typed downstream fields with source artifacts and support status; and
4. source artifacts and an optional superseded result digest.

The output is either a signed `protein_rna_discordance_downstream_export` result or a typed
abstention. A signed result contains an immutable `SignedDownstreamContract`, compatibility
report, evidence references, a canonical request/result digest pair, support decision,
limitations, and explicit uncertainty/provenance. An abstention contains no signed contract,
the blocking compatibility/support finding, and `human_review_required=true`.

The contract closes the following invariants:

- signed consumer identity equals the compatibility report consumer;
- every signed field owner is explicitly present in the ownership declaration;
- compatibility accepted-field IDs exactly equal signed field IDs;
- result ID is derived from the canonical request digest;
- evidence is non-empty and uses the evidence role;
- finding codes are unique;
- signed and abstained statuses cannot carry contradictory support/review state; and
- the result digest excludes only its own digest field and is replay-verifiable.

## Controls, uncertainty, and provenance

The preflight gate requires these seven upstream decisions in the expected state:

| Control | Required state |
| --- | --- |
| approved configuration | `accepted` |
| identity lineage | `resolved` |
| provenance | `accepted` |
| consent | `granted` |
| quality | `accepted` |
| support | `accepted` |
| intended use | `accepted` |

Every output declares all seven uncertainty dimensions: measurement, sampling, parameter,
model form, identification, support, and transport. Supported exports use an explicit 0.9
caller-declared probability and rationale; abstentions use `not_estimable` with a safe rationale.
Provenance carries the canonical request digest, input/configuration artifacts, and all seven
control decisions. Evidence is deduplicated by artifact digest while retaining stable ordering.

## Fail-closed behavior

The runtime abstains before promotion for missing, unknown, unsupported, not-evaluable, OOD,
abstain, prohibited-boundary, ownership, media, or review markers. Review/conflict/discrepancy
markers produce `review_required`; unsupported and boundary markers produce `incompatible`.
Malformed authorization mappings, failed strict parsing, forged plugin tokens, replay mismatch,
and tampered digests fail closed without exposing internal validation details through adapters.

## Interfaces and verification

- FastAPI: `GET /v1/m16-07/schema/{name}`, `POST /v1/modules/M16-07/export`,
  `POST /v1/modules/M16-07/verify`.
- Typer: `export-schema`, `export`, and `verify`; output paths are never overwritten.
- Plugin: strict parse-once validation produces a sealed `ValidatedM1607Request` token.
- Evaluator: ten frozen scenarios cover signed output, review/ownership/support abstention,
  prohibited boundaries, authorization, deterministic reconstruction, uncertainty/provenance,
  replay, and tamper rejection.
- Release verifier: `tools/verify_m1607_release.py` validates exact fixture closure, timing
  budgets, branch-enabled coverage, package hashes, and isolated import evidence.

## Explicit non-goals

This provisional module does not infer kinase state, treatments, identity, consent, mutation,
or relabel/erasure actions; does not perform generic all-omics fusion; and does not promote
unsupported negative findings. Endpoint names, media catalogues, and the final ABI remain subject
to the frozen contract decision.
