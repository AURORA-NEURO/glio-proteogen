# GLIO-PROTEOGEN-M17-08 — translation monitoring and rollback

M17-08 monitors caller-declared usage telemetry, support drift, workflow effects and
discrepancies beneath Metabolomic/lipidomic integration. It emits only a bounded
translation-health state and rollback decision for the `variant peptide` parent. The ABI is
explicitly provisional because the dossier defines behavior and architecture options rather
than a frozen field-level interface.

## Authority and boundary

| Property | Binding |
| --- | --- |
| Dossier SHA-256 | `sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181` |
| Exact slice | `GLIO-PROTEOGEN_240_Module_Dossier.md:6104-6144` |
| Owner / safety / gate | Platform engineering / S2 / G5 |
| Parent | `variant peptide` context only; `emits_parent=false` |
| Operation / version | `monitor_variant_peptide_translation_health` / `0.1.0-provisional` |
| Upstream boundary | Provisional M17-07 artifact reference only; content is never dereferenced |
| Primary / alternate / fallback | Event-driven baseline stack / typed network-factor hybrid / HITL signed package |
| Output ceiling | Health state, rollback decision, typed findings, support, uncertainty, provenance, evidence, limitations, or abstention |

M17-08 never performs KINOPHOS kinase-state work, generic all-omics fusion, treatment
recommendation, identity or consent inference, upstream mutation, disagreement erasure, or
unsupported-to-negative conversion. It quarantines unresolved declarations through explicit
review or abstention.

## Locked implementation and interfaces

- Seven caller-declared controls are preflighted before observations are evaluated.
- Telemetry, support drift, workflow effects and discrepancies are evaluated against the
  declared rollback threshold. Critical drift emits `rollback_required`; unresolved discrepancy
  emits `suspended`; warnings emit `degraded`; not-evaluable inputs abstain.
- Results are deterministic and replay-safe, with canonical request/result digests. No upstream
  artifact content is traversed or relabeled.
- All seven uncertainty dimensions are `not_estimable`; sensitivity and explicit abstention are
  preserved.

HTTP exposes `GET /v1/contracts/M17-08/{name}/schema` and
`POST /v1/modules/M17-08/translation-health`. CLI exposes
`m1708-translation-health export-schema NAME` and `m1708-translation-health monitor REQUEST`.
The plugin descriptor repeats the authority ceiling and provisional ABI.

The evaluator locks eight scenarios and eight adversarial cases; local evidence passes 8/8
(100%, target ≥95%). The benchmark performs one warm-up and 25 public monitor calls. Latency is
a software regression tripwire, not biological validation.

See the [module manifest](GLIO-PROTEOGEN-M17-08.manifest.md), [evidence inventory](../evidence/M17-08.md),
and [traceability matrix](../traceability/GLIO-PROTEOGEN-M17-08.csv).
