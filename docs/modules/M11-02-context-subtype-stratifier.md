# M11-02 — Context and subtype stratifier (provisional)

## Authority and scope

This implementation is grounded in `GLIO-PROTEOGEN-M11-02` dossier lines 3680–3720,
from dossier SHA-256 `0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`.
The dossier describes responsibility and acceptance behavior but does not freeze the
public ABI or context catalogue. Every public symbol, media type, and endpoint in this
lane is therefore explicitly `0.1.0-provisional`.

The module owns deterministic context mapping beneath Protein-native subtype inference:
disease class, subtype, age, territory, treatment era, specimen, platform, and biological
context. It emits only a typed context profile and mechanism-applicability set, preserving
the parent target `variant_peptide` without emitting that parent output.

The implementation does not own kinase state (KINOPHOS), generic all-omics fusion, direct
treatment recommendations, identity or consent inference, upstream mutation, disagreement
erasure, or unsupported-to-negative conversion. Source artifacts are opaque content-addressed
references; this module never traverses external payloads.

## Contract

`glio_proteogen.contracts.m11_02` defines strict frozen Pydantic models and JSON Schema
2020-12 exports for requests, observations, policies, rules, profiles, mechanism
applicability, diagnostics, and results. The request binds the provisional M11-01
hypothesis-registry media type, a locked policy, typed observations, and source artifacts.

Every result binds the exact canonical request digest and derives its result ID from that
digest. Evidence, seven-axis uncertainty, seven-control provenance, support status,
limitations, and human-review acknowledgement are mandatory. Abstained results never carry
a profile and never treat unsupported or missing context as a negative finding.

## Runtime and interfaces

`M1102ContextEngine` evaluates each declared policy rule deterministically. A supported,
allowed value yields `applicable`; low support yields `abstained`; missing, prohibited-proxy,
or outside-catalogue values yield `not_evaluable`. Any non-safe rule withholds the profile,
preserves diagnostics, marks support `review_required`, and requires human review.

`M1102Service` provides validation, JSON validation, execution, and replay verification.
`M1102Plugin` uses an opaque validate-then-run capability bound to the exact request object
and digest. `glio_proteogen.adapters.m1102` exposes strict raw-body FastAPI endpoints:

* `POST /v1/m11-02/schema/{contract}`
* `POST /v1/m11-02/validate`
* `POST /v1/m11-02/stratify`
* `POST /v1/m11-02/verify`

The Typer `m1102_app` exposes equivalent `export-schema`, `validate`, `stratify`, and
`verify` commands. Duplicate keys, non-finite values, malformed JSON, coercion, unknown
fields, and oversized bodies are rejected with sanitized diagnostics.

## Evidence gates

The locked synthetic evaluator covers supported stratification, low-support abstention,
missing context, prohibited proxies, exact replay, tamper rejection, denied consent, and
repeat determinism. The focused stage has 24 passing tests; scoped branch coverage is 99%
(529 statements, 78 branches); Ruff and strict MyPy are clean. The ten-call benchmark
receipt reports mean `1,897,050 ns`, median `1,732,500 ns`, and p95 `1,815,500 ns`, below
the provisional `2e9/3e9 ns` budgets.

The wheel and sdist are built with hatchling 1.31.0 and verified by an isolated-target
import check. Machine-readable receipts live under `release-evidence/m11_02/`.
