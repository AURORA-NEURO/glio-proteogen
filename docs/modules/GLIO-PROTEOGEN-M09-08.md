# GLIO-PROTEOGEN-M09-08 — evidence and explanation publisher

## Authority and ABI status

This implementation is mapped to dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact lines
3224–3267. The dossier names the responsibility and safety behavior but does not freeze
the upstream M09-07 endpoint, catalogue, operation media type, or result schema. All
M09-08 symbols and media types are therefore explicitly `0.1.0-provisional`, with owner
confirmation pending.

## Responsibility

M09-08 publishes a versioned complex-activity evidence bundle and explanation object with
input attribution, diagnostics, assumptions, counter-evidence, uncertainty, limitations,
provenance, and digest-closed reconstruction. It emits no parent claim (`emits_parent=false`)
and does not authenticate or traverse caller-owned payloads.

## Safety and ownership boundaries

- Consent, resolved identity lineage, approved configuration, provenance, quality, support,
  and intended-use controls are checked before publication.
- Missing source attribution, assumptions, counter-evidence, or reconstruction closure
  abstains with a typed support status; unsupported evidence is never converted to a negative.
- KINOPHOS kinase activity, generic all-omics fusion, direct treatment recommendation,
  identity inference, upstream mutation, and disagreement erasure are prohibited.
- Critical, unresolved, novel, OOD, or conflict counter-evidence marks the explanation for
  human review while retaining the counter-evidence.

## Implementation and evidence

| Surface | Artifact | Gate |
| --- | --- | --- |
| Contract | `src/glio_proteogen/contracts/m09_08` | strict Pydantic contracts, bounded collections, source/evidence uniqueness, exact request/result digests, replay closure |
| Runtime | `.../m09_08_evidence_explanation_publisher/engine.py` | deterministic content-addressed publication, explicit uncertainty, preflight, safe abstention, canonical replay |
| Interfaces | `api.py`, `cli.py`, `plugin.py`, `service.py` | strict parse-once API/CLI/plugin parity, sanitized errors, no-overwrite output |
| Tests | `tests/contract`, `tests/modules/c09_complex_stoichiometry`, `tests/integration` | 29 focused tests, adversarial closure, tamper, authorization, and parity coverage |
| Evaluator | `evals/m09_08/run.py` | publication, missing-attribution, missing-review-material, replay, tamper, determinism matrix |
| Benchmark | `evals/m09_08/benchmark.py` | 10 public publish calls; mean 3,143,930 ns, median 3,065,550 ns, p95 3,650,400 ns |

## Release interpretation

The evaluator and scoped branch coverage are engineering evidence, not scientific or clinical
validation. Scoped branch-enabled coverage is 99% (566 statements, 106 branches). Ruff and
compileall pass. A wheel (769,143 bytes, SHA-256
`f458ce09f5c2feb998d4fcf70b506c012488a237a2f78b5e1ae0f9acc40db8d9`) and sdist (1,436,875
bytes, SHA-256 `ec8d1af811a086b24bbefb85ba6176e602e2b99ee563ab1c409ed8ba778b1e74`) were built
with hatchling 1.31.0; the wheel was installed to a clean target and imported successfully.
External issuer authentication, biological validation, owner review, and promotion from the
provisional ABI remain required.
