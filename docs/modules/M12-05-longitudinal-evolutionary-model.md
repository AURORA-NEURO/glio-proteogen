# GLIO-PROTEOGEN-M12-05 module manifest

| Property | Provisional locked value |
| --- | --- |
| Module | GLIO-PROTEOGEN-M12-05 |
| Responsibility | Longitudinal and evolutionary model beneath the Driver-to-protein consequence map |
| Owner / safety / gate | Platform engineering / S2 / G2 |
| Parent target | `biomarker_panel` (`emits_parent=false`) |
| Version / ABI | `0.1.0-provisional`; dossier behavioral brief only, pending owner confirmation |
| Operation | `infer_biomarker_panel_longitudinal_evolution` |
| Input boundary | Opaque M12-04 network/state result, ordered time-point observations, locked model configuration, source artifacts, and seven caller controls |
| Output ceiling | Time-indexed trajectory and explicit change points, typed uncertainty, support, provenance, evidence, limitations, and abstention |
| Selected runtime | Additive typed glioma temporal program fit (damped Huber IRLS, smoothing/curvature, deterministic bootstrap) with the caller-declared grammar retained for compatibility |
| API | `GET /v1/m12-05/schema/{name}`; `POST /v1/modules/M12-05/longitudinal`; `POST /v1/modules/M12-05/verify` |
| CLI | `m1205_app export-schema NAME`; `m1205_app infer REQUEST [--output RESULT]`; `m1205_app verify RESULT` |
| Schemas | `request`, `output`, `observation`, `trajectory-state`, `change-point`, `configuration`, `policy`, `diagnostic` |

## Authority and scope

This implementation is bound to dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
M12-05 lines 4172–4212. The dossier does not freeze endpoint names, wire media
types, catalogue identifiers, or estimator ABI; every public symbol and
package identifier in this lane is marked provisional. The typed runtime is a
repository-native research model and does not claim clinical validity,
authenticated issuer authority, calibrated population coverage, or biological
truth. Opaque objective requests remain metadata-only for compatibility.

M12-05 accepts only caller-declared references. It never opens the M12-04
result, proteome, genome/transcriptome, PTM, model, or source artifact content.
Identity, lineage, consent, provenance, quality, support, approved
configuration, and intended-use state are validated before objective parsing.
Observation sequence and timestamp ordering are validated at the contract
boundary, preventing future leakage and preserving temporal reproducibility.

## Objective and output semantics

Typed observations may opt into the research-only glioma lane by supplying a
program, standardized effect, standard error, quality weight, and explicit
evidence state. The solver fits five glioma programs independently over the
ordered history, aggregates their latent state, and emits bounded intervals,
stability, discordance, evidence counts, and top program drivers. It uses a
one-sided loss for left-censored evidence and ignores missing/unsupported
observations. Deterministic NumPy PCG64 perturbations are seeded from the
canonical request digest; the objective-trace digest binds the complete solver
path for replay. A change point is detected only when its bootstrap signed delta
clears the configured threshold. This is an experimental molecular signal and
does not assert tumor evolution, clinical risk, or treatment response.

The selected deterministic reference boundary accepts exactly `stable`,
`alternating`, `territory`, `treatment_era`, `time_course`, their
`trajectory:<mode>` aliases, and `change_point:<sequence>:<before>:<after>`.
Each supported observation becomes one ordered trajectory state with an
explicit research interval and evidence. A valid change-point objective emits
one explicit detected change point with before/after state references. Typed
starts use observed centers projected onto tightest left-censor limits; censor-
only points start at the ridge-neutral feasible value before smoothing.

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
