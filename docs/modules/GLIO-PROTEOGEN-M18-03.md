# GLIO-PROTEOGEN-M18-03 — fusion and aggregation engine

M18-03 performs component-specific fusion beneath Spatial proteomics projection while
preserving source identity, reliability, uncertainty, disagreement and ownership. It emits
only an integrated evidence object for the `biomarker panel` parent. The ABI is explicitly
provisional because the dossier defines behavior and architecture options rather than a frozen
field-level interface.

## Authority and boundary

| Property | Binding |
| --- | --- |
| Dossier SHA-256 | `sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181` |
| Exact slice | `GLIO-PROTEOGEN_240_Module_Dossier.md:6244-6284` |
| Owner / safety / gate | ML engineering / S2 / G2 |
| Parent | `biomarker panel` context only; `emits_parent=false` |
| Operation / version | `fuse_biomarker_panel_evidence` / `0.1.0-provisional` |
| Upstream boundary | Provisional M18-02 alignment reference only; content is never dereferenced |
| Primary / alternate / fallback | Event-driven pathway activity network / signed pathway propagation / HITL protein-complex graph |
| Output ceiling | Integrated evidence with source attribution, reliability, uncertainty, disagreement, provenance, evidence, limitations, or abstention |

M18-03 never performs KINOPHOS kinase-state work, generic all-omics fusion, treatment
recommendation, identity or consent inference, upstream mutation, disagreement erasure, or
unsupported-to-negative conversion. Unresolved, low-reliability or ownership-unsafe inputs
abstain and remain reviewable.

## Locked implementation and interfaces

- Seven caller-declared controls are preflighted before source contributions or disagreements are
  traversed.
- Component contributions retain source ID, kind, owner, artifact, claim, reliability score and
  evidence. Resolved disagreements remain in the integrated object; unresolved disagreements
  abstain rather than being erased.
- Reliability below the configured threshold, non-evaluable sources and forbidden ownership
  claims produce typed findings and no integrated object.
- Results are deterministic and replay-safe, with canonical request/result digests. All seven
  uncertainty dimensions are `not_estimable`.

HTTP exposes `GET /v1/contracts/M18-03/{name}/schema` and
`POST /v1/modules/M18-03/fusion`. CLI exposes `m1803-fusion export-schema NAME` and
`m1803-fusion fuse REQUEST`. The plugin descriptor repeats the authority ceiling and provisional
ABI.

The evaluator locks eight scenarios and eight adversarial cases; local evidence passes 8/8
(100%, target ≥95%). The benchmark performs one warm-up and 25 public fusion calls. Latency is
a software regression tripwire, not biological validation.

See the [module manifest](GLIO-PROTEOGEN-M18-03.manifest.md), [evidence inventory](../evidence/M18-03.md),
and [traceability matrix](../traceability/GLIO-PROTEOGEN-M18-03.csv).
