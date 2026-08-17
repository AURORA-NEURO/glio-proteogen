# GLIO-PROTEOGEN-M28-04 module manifest

| Property | Provisional value |
| --- | --- |
| Module | `GLIO-PROTEOGEN-M28-04` |
| Title | API / SDK / CLI gateway for caller-declared proteotype explanation access |
| Parent | `proteotype explanation report` |
| Owner / safety / gate | Data engineering / S3 / G2 |
| Authority | Dossier SHA `0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, lines `9888-9928` |
| ABI status | `0.1.0-provisional`; behavioral brief only; pending owner confirmation |
| Public operation | `publish_protein_rna_discordance_access_surface` |
| Input | Caller-declared typed operations, authorization, idempotency, asynchronous jobs, compatibility, errors, audit, artifacts, configuration, and execution controls |
| Output ceiling | A typed access metadata surface or explicit abstention with findings, support state, provenance, uncertainty, and replay evidence |
| Protocols | API, SDK, and CLI; each operation is enabled explicitly by configuration |
| Fallback | Offline signed release-bundle support is declared as metadata only; this module does not sign, authenticate, or traverse external content |
| Model count | Zero; no external model, registry, object store, event log, or scientific-file traversal |
| Prohibited | Protein/proteoform/isoform or glioma-specific biological inference, kinase activity, generic all-omics fusion, treatment recommendation, identity inference, and consent inference |

## Implementation depth

The gateway is deliberately deterministic and caller-declared. Contract models close every
operation, authorization, idempotency, job, compatibility, error, audit, and configuration
reference before publication. Canonical request/result bytes derive stable request digests,
result identifiers, and replay-verifiable result digests. Publication returns `PUBLISHED` only
when the seven execution controls, authorization, asynchronous state, compatibility, and audit
requirements are satisfied; otherwise it returns a typed `ABSTAINED` result and retains the
finding rather than converting uncertainty into a negative claim.

The service parses once at the boundary. API, SDK, CLI, and strict JSON plugin routes share the
same service and replay implementation, reject malformed or oversized payloads, and sanitize
errors. Hostile mapping-like objects, forged plugin seals, mismatched cross-references, tampered
result identities, and unsupported states are covered by adversarial tests.

## Release evidence

- Python additions in the M28-04 implementation/evaluator paths: **2,073 lines**.
- Focused Python test additions: **914 lines**; total M28-04 Python additions: **2,987 lines**.
- Focused suite: **35 passed**.
- Ruff check/format: **passed**.
- MyPy strict: **21 targeted files passed**.
- Compileall: **passed**.
- Branch-enabled scoped coverage: **95.25222551928783%** (`830/861` statements and `133/150` branches; `963/1011` weighted), fail-under `95`.
- Evaluator: **10/10** checks passed; fixture digest `sha256:f3a681830908eaf1ab86163b4c002d5a287dd9363ff3cd8710503c9af8fd9c22`.
- Ten-iteration benchmark: mean `2,113,360 ns`, p95 `2,663,800 ns`; budgets `500,000,000/750,000,000 ns`.
- Package: reproducible wheel/sdist sizes, hashes, member counts, and isolated-import results are recorded in the excluded machine-readable record `docs/evidence/m28_04/package.json`; generated temporary artifacts audit to zero.
- Release evidence verifier: passed.

Repository Actions billing/spending-limit failures, when present before any job steps, are
external CI provisioning blockers and do not invalidate these local gates.
