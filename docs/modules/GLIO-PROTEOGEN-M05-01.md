# GLIO-PROTEOGEN-M05-01 — PTM-localization protocol and metadata specification

M05-01 is a strict, metadata-only G0 conformance boundary beneath a future PTM-localization
interface. It validates caller-declared controlled vocabularies, mandatory fields, units,
assay/specimen versions, cardinality, compatibility, unresolved-state actions, and the metadata
receipt needed by the parent target `variant_peptide`. It never opens scientific artifacts and
does not localize a PTM or emit a variant peptide.

## Public boundary

- Python operation: `evaluate_ptm_localization_protocol`
- Request: `EvaluatePtmLocalizationProtocolRequest`
- Result: `PtmLocalizationProtocolConformanceResult`
- HTTP: `POST /v1/modules/M05-01/protocol-conformance`
- Schema HTTP: `GET /v1/contracts/M05-01/{name}/schema`
- CLI: `m05-01-validate PATH` and `m05-01-export-schema NAME`
- Contract/schema version: `1.0.0`, JSON Schema 2020-12

The request carries one immutable protocol schema, one independently reviewed conformance profile,
and all seven caller-declared control decisions. Three scientific roles are references only:
mass-spectrometry proteome, genome/transcriptome, and PTM annotations. The module neither fetches nor
parses their content. M04-05 is not consumed because the authoritative M05-01 dossier slice declares
no M04-05 dependency.

## Decision semantics

| Status | Disposition | Meaning |
|---|---|---|
| `conformant` | `conformant` | The protocol lies in the reviewed support domain and every section passes. |
| `nonconformant` | `quarantined` | A supported declaration fails a hard metadata invariant; external review is required. |
| `indeterminate` | `abstained` | Version, assay/specimen, reference, vocabulary, unit, or policy support is unreviewed, unresolved, novel, or OOD. No negative finding is emitted. |

Every result has exactly eight findings: identity, versions, units, completeness, assay support,
parent quality, compatibility, and unresolved semantics. Result, request, protocol, profile,
configuration, reference bundle, assay/specimen policy, section, finding, receipt, evidence, and
provenance bindings are deterministic and replayed during strict result reconstruction.

## Machine-validatable protocol

The conformant declaration contains:

- seven identity keys and ten distinct unresolved states;
- exactly one reference for each of the three scientific input roles plus a manifest;
- controlled vocabulary entries with opaque IDs and closed meanings;
- six quantity/unit pairs: dalton, thomson, minute, parts per million, probability parts per million,
  and count;
- eight mandatory singleton metadata-field policies;
- reviewed assay/specimen policy and four required compatibility relationships;
- six metadata-only parent receipt roles for `variant_peptide`.

All values are strict: unknown fields, duplicate JSON keys, coercion, non-finite numbers, alias/digest
mismatch, non-allowlisted media types, stale configuration, stale profile pins, future review time,
and request/context identity splits reject. Canonical semantic collections reorder without changing
the request or result.

Installed collection ceilings are algebraically constructible: 32 approved reference bundles, 16
items in each approved version collection, 16 controlled vocabularies, 12 terms per vocabulary, six
unit policies, eight metadata fields, and 32 compatibility rules. Canonical request size is capped at
4 MiB. The genuine maximum fixture exercises every ceiling and produces a valid result.

## Authorization and safe failure

The runtime performs a content-free seven-control preflight before protocol or profile traversal.
Approved configuration, provenance, quality, support, and intended use must be accepted; identity
must be resolved; consent must be granted. A denied control raises one sanitized authorization error.
Ordinary hostile exceptions fail closed, arbitrary mappings/accessors are not traversed, and
`BaseException` is not swallowed.

After authorization, one duplicate-free bounded JSON parse is materialized through exact built-in
containers. Plugin validation issues a weak token bound to the original request identity and exact
canonical byte snapshot. Copied seals, copied requests, mutated requests, and handwritten tokens
cannot invoke the private validated execution path.

## Uncertainty and claims ceiling

All seven uncertainty dimensions are explicit and `not_estimable`; M05-01 has no measurements,
samples, fitted parameters, learned model, identification authority, calibrated probability, or
transport qualification. Sensitivity text narrows the support domain and states that unsupported or
OOD declarations abstain. This satisfies the G3 calibration alternative by narrowing support rather
than claiming nominal 90% coverage.

All authority flags are literal false. M05-01 emits no PTM localization, variant peptide,
proteogenomic state, proteotype, protein-level subtype, kinase activity, generic all-omics fusion,
treatment recommendation, identity, or consent conclusion. It never mutates upstream evidence,
relabels another module, erases disagreement, or treats missing/unsupported evidence as negative.

## Architecture decision

The dossier lists schema-first, event-sourced, quarantine-first, PCA/ICA, and sparse-NMF variants.
At G0 this implementation selects deterministic schema-first batch conformance only. The other
options are recorded as `declared_not_executed`; there is no model dependency, fit, weight, score,
event log, object store, network lookup, or external service.

## Verification

The locked fixture contains exactly eight groups of five unique cases. The evaluator proves all 40
declared cases execute exactly once. The benchmark performs one untimed maximum-shape warm-up and
exactly 25 timed public calls; mean must be at most 2 seconds and nearest-rank p95 at most 3 seconds.
Focused tests cover strict contracts, hostile ingress, complete replay, forgery, privacy, recovery,
and Python/HTTP/CLI parity. The release verifier rejects incomplete corpus or benchmark evidence.

See [the module manifest](M05-01.manifest.md), [evidence inventory](../evidence/M05-01.md), and
[traceability matrix](../traceability/GLIO-PROTEOGEN-M05-01.csv).
