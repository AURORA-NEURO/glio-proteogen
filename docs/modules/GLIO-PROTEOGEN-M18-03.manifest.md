# GLIO-PROTEOGEN-M18-03 module manifest

| Property | Locked value |
| --- | --- |
| Module / component | GLIO-PROTEOGEN-M18-03 / C18 spatial proteomics projection |
| Responsibility | Component-specific fusion and aggregation with source attribution, reliability and disagreement preservation |
| Owner / safety / gate | ML engineering / S2 / G2 |
| Version / ABI | 0.1.0-provisional / dossier-behavioral-brief-only |
| Dossier binding | SHA-256 `0A6B200CBE073DB13A4BCF315EDC23AB97EDFE6F500BC7EA2785F5E1C70DA181`; lines 6244-6284 |
| Runtime | Stateless deterministic fusion; no persistence, raw-content traversal or model execution |
| Primary architecture | Event-driven reliability-aware orchestration + pathway activity network (declared, not executed) |
| Alternate / fallback | Typed service + signed pathway propagation / HITL signed package + protein-complex graph (declared, not executed) |
| API | GET `/v1/contracts/M18-03/{name}/schema`; POST `/v1/modules/M18-03/fusion` |
| CLI | `m1803-fusion export-schema NAME`; `m1803-fusion fuse REQUEST` |
| Schemas | request, output, integrated-evidence, source-contribution, disagreement, aggregation, configuration, finding |
| Parent ceiling | `biomarker panel` context only; no parent emission, kinase, treatment, diagnosis, subtype or all-omics inference |
| Capacity | 128 contributions, 128 disagreements, 256 aggregates, 64 evidence/findings, 4 MiB request, 8 MiB result |

## Data, model and authority manifest

Fixtures are synthetic, non-clinical, opaque metadata. The M18-02 alignment value is a typed
content reference and is never opened. Contributions, reliability, ownership, disagreements,
configuration, seven controls, evidence and uncertainty are caller-declared; they do not
authenticate issuer authority, consent truth, identity, measurement execution or biological
truth. All dossier architecture names are declared-not-executed.

The evaluator fixture is `tests/fixtures/m18_03/scenarios.json`; `evals/m18_03/run.py` executes
eight scenarios and eight adversarial cases. The benchmark constructs one attributable request
outside timing and measures exactly 25 public fusion calls with software-only budgets.

## Review and recovery

M18-03 cannot self-approve. Critical discrepancy, novel/OOD state, support override, claim
promotion, release exception and unresolved biological conflict remain external review work.
Recovery is append-only: retain immutable request/result and publish a corrected superseding
result without deleting, mutating, relabeling or silently promoting input.
