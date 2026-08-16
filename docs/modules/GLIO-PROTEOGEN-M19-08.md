# GLIO-PROTEOGEN-M19-08: translation monitoring and rollback

M19-08 is a provisional, deterministic monitoring boundary beneath Immunopeptidomic
evidence. It consumes a caller-declared M19-07 downstream typed export and records
translation health across usage telemetry, support drift, workflow effects, and
discrepancies. It may produce a bounded health state and rollback decision, or it
abstains safely when support, controls, or required observations are not evaluable.

## Authority and scope

| Property | Locked value |
| --- | --- |
| Module | GLIO-PROTEOGEN-M19-08 |
| Title | Translation monitoring and rollback |
| Dossier binding | `GLIO-PROTEOGEN_240_Module_Dossier.md:6824-6864` |
| Dossier SHA-256 | `0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181` |
| Owner | Computational biology |
| Safety / evidence gate | S2 / G5 |
| Parent context | `proteotype` |
| Operation | `monitor_proteotype_translation_health` |
| ABI status | `0.1.0-provisional`; no frozen endpoint or catalogue is implied |
| Upstream media boundary | `application/vnd.glio-proteogen.m19-07+json` |
| Output media boundary | `application/vnd.glio-proteogen.m19-08+json` |

The module does not infer upstream mutation, identity, consent, or treatment. It does
not own kinase activity, generic all-omics fusion, or clinical decision-making. It does
not erase disagreement, convert missing evidence into a negative finding, authenticate
an issuer, or promote a translation-health state into a biological or clinical claim.

## Contract and runtime boundary

The strict request binds one M19-07 artifact, unique source artifacts, telemetry,
support-drift observations, workflow effects, discrepancies, a locked rollback policy,
and a caller-declared support decision. Every observation and rollback-policy evidence
reference must resolve to a source artifact. Observation and discrepancy identifiers
are globally unique across categories. Numeric measurements are finite and bounded;
unknown fields, coercion, duplicate JSON keys, and excess collections reject.

The runtime performs seven-control authorization before traversing governed request
content. It classifies only the declared observations, preserving the distinction
between healthy, degraded, suspended, rollback-required, and not-evaluable states.
Critical failures reach rollback only when the locked threshold is met. Unresolved
discrepancy requests suspension; warnings produce review-required degradation; missing
or unsupported support produces an explicit abstention with no health report.

Every result contains a canonical request digest, result digest, typed support decision,
seven explicit not-estimable uncertainty dimensions, provenance, evidence, limitations,
finding codes, and immutable replay material. Replaying the exact request must reproduce
the result; tampered identifiers, payloads, digests, or replay state are rejected. A
rollback decision is a decision record only: recovery is append-only and requires an
externally governed superseding request and review.

## Interfaces

| Surface | Boundary |
| --- | --- |
| Python | `monitor_proteotype_translation_health(request)` |
| Service | `M1908Service.execute`, `verify`, `replay` |
| Plugin | strict JSON parse-once token, `run`, `verify`, `replay` |
| FastAPI | `POST /v1/modules/M19-08/translation-health`; schema GET |
| Typer | `glio-proteogen m1908-translation-health monitor`; schema export |

The API and CLI accept only strict JSON metadata. Plugin tokens are instance-bound and
cannot be forged by copying a token seal. No interface accepts raw scientific files,
follows artifact paths, writes over an existing output, or bypasses authorization and
replay validation.

## Evidence and limitations

The locked fixture contains eight named scenarios and eight adversarial cases, with a
95 percent adversarial target. The executable evaluator passed all scenarios and all
adversarial cases. The focused contract, runtime, interface, evaluator, and adversarial
suite contains 38 passing tests. Scoped branch-enabled coverage is 96 percent over 488
statements and 84 branches. The 25-iteration benchmark times only the deterministic
engine call after construction and warm-up; the observed mean was approximately 2.9 ms
and p95 approximately 3.3 ms against provisional 500 ms / 750 ms budgets.

These results establish software contract and deterministic control-flow behavior for
synthetic caller-declared metadata only. They do not establish telemetry truth, support
drift validity, model accuracy, calibration, transportability, rollback safety in an
external deployment, reviewer authority, scientific validity, or clinical utility.

See the [evidence inventory](../evidence/M19-08.md) and [traceability matrix](../traceability/GLIO-PROTEOGEN-M19-08.csv).
