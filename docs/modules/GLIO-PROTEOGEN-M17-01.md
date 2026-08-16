# GLIO-PROTEOGEN-M17-01 — upstream contract resolver

M17-01 resolves caller-declared upstream compatibility beneath the `variant peptide` parent.
It validates typed discovery, version/media compatibility, consent, intended use, support,
provenance, and uncertainty, then emits a validated upstream bundle or an explicit abstention.
The ABI remains provisional because the dossier provides a behavioral brief rather than a frozen
field-level interface.

## Authority and boundary

| Property | Binding |
| --- | --- |
| Dossier SHA-256 | `sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181` |
| Exact slice | `GLIO-PROTEOGEN_240_Module_Dossier.md:5796-5836` |
| Owner / safety / gate | Scientific engineering / S2 / G0 |
| Parent | `variant peptide` context only; `emits_parent=false` |
| Operation / version | `resolve_variant_peptide_upstream_contracts` / `0.1.0-provisional` |
| Primary / alternate / fallback | Bayesian factor analysis / PCA-ICA baseline / PCA-ICA baseline (declared, not executed) |
| Input ceiling | MS proteome, genome/transcriptome, PTM annotations, approved configuration, identity/lineage, provenance, consent, quality, support, intended use |
| Output ceiling | Validated upstream bundle, closed compatibility report, typed findings, seven-dimensional uncertainty, provenance, evidence, limitations, or abstention |

The runtime never opens external content, performs all-omics fusion, computes kinase activity,
recommends treatment, infers identity or consent, mutates upstream declarations, erases
disagreement, or turns unsupported/unknown evidence into a negative finding. Unknown candidates
remain unresolved; incompatible or unconfigured candidates are typed rejections. Any failed
control is rejected before candidate traversal and requires external review.

## Locked implementation

- Strict frozen request/result models preserve every candidate outcome and content-bound digest.
- Seven controls are preflighted before typed validation and traversal.
- Compatible candidates require granted consent, supported status, provenance, and a matching
  locked source-kind/media/intended-use rule.
- Results are deterministic and replay-safe. Tampering with the request or derived payload is
  rejected; corrected work is append-only and never overwrites prior evidence.
- All seven uncertainty dimensions are `not_estimable`; no probability or scientific calibration
  is claimed. Explicit abstention carries review-required support and no bundle.

## Interfaces and evidence

HTTP exposes `GET /v1/contracts/M17-01/{name}/schema` and
`POST /v1/modules/M17-01/upstream-contract-resolution`. CLI exposes
`m1701-upstream export-schema NAME` and `m1701-upstream resolve REQUEST`. The plugin descriptor
repeats the authority ceiling and provisional ABI.

The evaluator locks five executable scenarios and eight adversarial control/boundary cases;
local evidence passes 8/8 (100%, target ≥95%). The benchmark performs one warm-up and 25 public
`M1701Engine.resolve` calls over a mixed compatible/rejected/unknown workload. Its latency bounds
are software regression tripwires only, not scientific validation.

See the [module manifest](GLIO-PROTEOGEN-M17-01.manifest.md), [evidence inventory](../evidence/M17-01.md),
and [traceability matrix](../traceability/GLIO-PROTEOGEN-M17-01.csv).
