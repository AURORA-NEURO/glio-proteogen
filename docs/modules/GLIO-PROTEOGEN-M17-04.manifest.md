# GLIO-PROTEOGEN-M17-04 module manifest

| Property | Locked value |
| --- | --- |
| Module / component | GLIO-PROTEOGEN-M17-04 / C17 metabolomic/lipidomic integration |
| Responsibility | Intended-use, audience, evidence-tier, claim-ceiling, and display-policy adaptation |
| Owner / safety / gate | ML engineering / S2 / G3 |
| Version / ABI | 0.1.0-provisional / dossier-behavioral-brief-only |
| Dossier binding | SHA-256 `0A6B200CBE073DB13A4BCF315EDC23AB97EDFE6F500BC7EA2785F5E1C70DA181`; lines 5928-5968 |
| Runtime | Stateless deterministic policy adapter; no persistence, raw-content traversal, or model execution |
| Primary architecture | Variant-peptide graph (declared, not executed) |
| Alternate / fallback | PTM-aware state model / proteoform probabilistic model (declared, not executed) |
| API | GET `/v1/contracts/M17-04/{name}/schema`; POST `/v1/modules/M17-04/intended-use-adaptation` |
| CLI | `m1704-intended-use export-schema NAME`; `m1704-intended-use adapt REQUEST` |
| Schemas | request, output, claim-ceiling, display-semantics, registration, policy-decision, object, finding |
| Parent ceiling | `variant peptide` context only; no parent emission, kinase, treatment, diagnosis, subtype, or all-omics inference |
| Capacity | 64 prohibited interpretations/evidence/findings; 32 display sections; 4 MiB request; 8 MiB result |

## Data, model, and authority manifest

Fixtures are synthetic, non-clinical, opaque metadata. The M17-03 upstream value is a typed
content reference and is never opened. Registration, claim ceiling, display semantics, seven
controls, support, provenance, evidence and uncertainty are caller-declared; they do not
authenticate issuer authority, consent truth, identity, measurement execution, or biological
truth. All dossier architecture names are declared-not-executed.

The evaluator fixture is `tests/fixtures/m17_04/scenarios.json`; `evals/m17_04/run.py` executes
seven scenarios and eight adversarial cases. The benchmark constructs one registered research
request outside timing and measures exactly 25 public adapter calls with software-only budgets.

## Review and rollback

M17-04 cannot self-approve. Release evidence must name an externally authenticated reviewer and
bind the dossier hash/slice, source commit, schema and fixture digests, evaluator/benchmark
digests, interface tests, and request/result digests. Claim promotion, support override, release
exception, novel/OOD state, or unresolved conflict remains external review work. Recovery is
append-only: retain immutable request/result and publish a corrected superseding result without
deleting, mutating, relabeling, or silently promoting input.
