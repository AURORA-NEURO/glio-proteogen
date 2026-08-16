# GLIO-PROTEOGEN-M13-05 module manifest

| Property | Provisional locked value |
| --- | --- |
| Module | GLIO-PROTEOGEN-M13-05 |
| Responsibility | Longitudinal and evolutionary model beneath the Variant-peptide channel |
| Owner / safety / gate | Scientific engineering / S2 / G2 |
| Parent target | `proteotype` (`emits_parent=false`) |
| Version / ABI | `0.1.0-provisional`; dossier behavioral brief only, pending owner confirmation |
| Operation | `infer_proteotype_longitudinal_evolution` |
| Input boundary | Opaque M13-04 state result, ordered time-point observations, locked model configuration, source artifacts, and seven caller controls |
| Output ceiling | Time-indexed trajectory and explicit change points, typed uncertainty, support, provenance, evidence, limitations, and abstention |
| Selected runtime | Deterministic caller-declared trajectory grammar with replay-bound canonical digests |
| API | `GET /v1/m13-05/schema/{name}`; `POST /v1/modules/M13-05/longitudinal`; `POST /v1/modules/M13-05/verify` |
| CLI | `m1305_app export-schema NAME`; `m1305_app infer REQUEST [--output RESULT]`; `m1305_app verify RESULT` |
| Schemas | `request`, `output`, `observation`, `trajectory-state`, `change-point`, `configuration`, `policy`, `diagnostic` |

## Authority and scope

This implementation is bound to dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
M13-05 lines 4532–4575. The dossier does not freeze endpoint names, wire media
types, catalogue identifiers, or estimator ABI; every public symbol and
package identifier in this lane is marked provisional. The implementation is
metadata-only and does not claim clinical validity, authenticated issuer
authority, calibrated population coverage, or biological truth.

M13-05 accepts only caller-declared references. It never opens the M13-04
result, proteome, genome/transcriptome, PTM, model, or source artifact content.
Identity, lineage, consent, provenance, quality, support, approved
configuration, and intended-use state are validated before objective parsing.
Observation sequence and timestamp ordering are validated at the contract
boundary, preventing future leakage and preserving temporal reproducibility.

## Objective and output semantics

The selected deterministic reference boundary accepts `stable`, `alternating`,
`territory`, `treatment_era`, `time_course`, `primary_recurrence`, `clone`,
`state_transition`, their `trajectory:<mode>` aliases, and
`change_point:<sequence>:<before>:<after>`. Each supported observation becomes
one ordered trajectory state with an explicit posterior placeholder and
evidence. A valid change-point objective emits one explicit detected change
point with before/after state references.

Unknown objectives, invalid change-point support, denied controls, malformed
requests, or unsafe histories produce no trajectory and no negative biological
finding. They return a typed review-required support decision, explicit
abstention reason, seven non-estimable uncertainty dimensions, diagnostics,
limitations, and `human_review_required=true`.

Every result retains the seven uncertainty dimensions (measurement, sampling,
parameter, model-form, identification, support, transport), sensitivity notes,
seven control-decision provenance records, evidence references, canonical
request digest, and canonical result digest. Replay reconstructs the exact
result from the request; tampering is rejected as a safe error.

## Ownership exclusions and recovery

The module emits no kinase activity (KINOPHOS ownership), generic all-omics
fusion, direct treatment recommendation, identity inference, consent
inference, upstream relabeling, disagreement erasure, or parent-output
mutation. External content traversal is false in every exported schema.

Recovery is deterministic replay plus explicit human review; no overwrite,
persistence, or external side effect is performed by the runtime. Package
evidence records wheel/sdist hashes, member counts, and isolated import
verification. Owner review, synthetic truth, negative-control qualification,
and calibration evidence remain required before ABI promotion.
