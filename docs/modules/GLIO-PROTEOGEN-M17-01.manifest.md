# GLIO-PROTEOGEN-M17-01 module manifest

| Property | Locked value |
| --- | --- |
| Module / component | GLIO-PROTEOGEN-M17-01 / C17 metabolomic/lipidomic integration |
| Responsibility | Typed upstream discovery and compatibility resolution for the variant-peptide parent |
| Owner / safety / gate | Scientific engineering / S2 / G0 |
| Version / ABI | 0.1.0-provisional / dossier-behavioral-brief-only |
| Dossier binding | SHA-256 `0A6B200CBE073DB13A4BCF315EDC23AB97EDFE6F500BC7EA2785F5E1C70DA181`; lines 5796-5836 |
| Runtime | Stateless deterministic typed resolver; no persistence, raw-content traversal, or model execution |
| Primary architecture | Bayesian factor analysis (declared, not executed) |
| Alternate / fallback | PCA/ICA baseline (declared, not executed) |
| API | GET `/v1/contracts/M17-01/{name}/schema`; POST `/v1/modules/M17-01/upstream-contract-resolution` |
| CLI | `m1701-upstream export-schema NAME`; `m1701-upstream resolve REQUEST` |
| Schemas | request, output, candidate, compatibility-rule, compatibility-decision, compatibility-report, configuration, bundle, finding |
| Parent ceiling | `variant peptide` context only; no parent emission, kinase, fusion, treatment, identity, or all-omics inference |
| Capacity | 128 candidates, 64 rules/evidence, 64 findings, 4 MiB request, 8 MiB result |

## Data and authority manifest

All fixtures are synthetic, non-clinical, opaque metadata. Candidate artifacts are references only;
the resolver does not dereference them. Seven control references, candidate evidence, provenance,
support, intended-use and uncertainty are retained as typed declarations. These declarations do
not authenticate issuer authority, consent truth, identity, assay execution, external content, or
biological truth.

The evaluator fixture is `tests/fixtures/m17_01/scenarios.json`; `evals/m17_01/run.py` executes
five scenarios and verifies eight adversarial cases. The benchmark fixture is constructed outside
the timed region; exactly 25 public resolver calls are measured. A 500 ms mean and 750 ms p95
software budget is used as a regression tripwire only.

## Review and rollback

M17-01 cannot self-approve. Release evidence must name an externally authenticated reviewer and
bind the dossier hash/slice, source commit, schema and fixture digests, evaluator/benchmark
digests, interface tests, and exact result/request digests. Control denial, unknown/OOD input,
support override, claim promotion, release exception, or unresolved biological conflict remains
external review work. Recovery is append-only: retain the immutable request/result and publish a
corrected superseding result without deleting, mutating, relabeling, or silently promoting input.
