# GLIO-PROTEOGEN-M17-08 module manifest

| Property | Locked value |
| --- | --- |
| Module / component | GLIO-PROTEOGEN-M17-08 / C17 metabolomic/lipidomic integration |
| Responsibility | Translation-health monitoring, support drift, workflow effects, discrepancies, suspension and rollback |
| Owner / safety / gate | Platform engineering / S2 / G5 |
| Version / ABI | 0.1.0-provisional / dossier-behavioral-brief-only |
| Dossier binding | SHA-256 `0A6B200CBE073DB13A4BCF315EDC23AB97EDFE6F500BC7EA2785F5E1C70DA181`; lines 6104-6144 |
| Runtime | Stateless deterministic monitor; no persistence, raw-content traversal, or model execution |
| Primary architecture | Event-driven reliability-aware orchestration + baseline stack (declared, not executed) |
| Alternate / fallback | Typed service integration + network-factor hybrid / HITL signed review + baseline stack (declared, not executed) |
| API | GET `/v1/contracts/M17-08/{name}/schema`; POST `/v1/modules/M17-08/translation-health` |
| CLI | `m1708-translation-health export-schema NAME`; `m1708-translation-health monitor REQUEST` |
| Schemas | request, output, health-report, telemetry, support-drift, workflow-effect, discrepancy, rollback-policy, finding |
| Parent ceiling | `variant peptide` context only; no parent emission, kinase, treatment, diagnosis, subtype, or all-omics inference |
| Capacity | 256 telemetry, 128 support/workflow/discrepancies, 64 evidence/findings, 4 MiB request, 8 MiB result |

## Data, model, and authority manifest

Fixtures are synthetic, non-clinical, opaque metadata. The M17-07 upstream value is a typed
content reference and is never opened. Telemetry, support drift, workflow effects, discrepancies,
rollback policy, seven controls, evidence and uncertainty are caller-declared; they do not
authenticate issuer authority, consent truth, identity, measurement execution, or biological
truth. All dossier architecture names are declared-not-executed.

The evaluator fixture is `tests/fixtures/m17_08/scenarios.json`; `evals/m17_08/run.py` executes
eight scenarios and eight adversarial cases. The benchmark constructs one healthy request outside
timing and measures exactly 25 public monitor calls with software-only budgets.

## Review and rollback

M17-08 cannot self-approve. Critical discrepancy, novel/OOD state, support override, claim
promotion, release exception and unresolved biological conflict remain external review work.
Recovery is append-only: retain immutable request/result and publish a corrected superseding
result without deleting, mutating, relabeling or silently promoting input.
