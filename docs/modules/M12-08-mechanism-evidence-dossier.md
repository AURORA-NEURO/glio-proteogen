# GLIO-PROTEOGEN-M12-08 module manifest

| Property | Provisional locked value |
| --- | --- |
| Module | GLIO-PROTEOGEN-M12-08 |
| Responsibility | Mechanism evidence dossier beneath the Driver-to-protein consequence map |
| Owner / safety / gate | Bioinformatics / S2 / G3 |
| Parent target | `biomarker_panel` (`emits_parent=false`) |
| Version / ABI | `0.1.0-provisional`; dossier behavioral brief only, pending owner confirmation |
| Operation | `assemble_biomarker_panel_mechanism_dossier` |
| Input boundary | Opaque M12-07 result, proteome/genome/transcriptome/PTM references, locked configuration, source artifacts, and seven caller controls |
| Output ceiling | Review-ready chain, counter-evidence, validation route, seven-dimensional uncertainty, claim ceiling, provenance, limitations, and abstention |
| Selected runtime | Deterministic closed architecture grammar with replay-bound canonical digests |
| API | `GET /v1/m12-08/schema/{name}`; `POST /v1/modules/M12-08/mechanism-dossier`; `POST /v1/modules/M12-08/verify` |
| CLI | `m1208_app export-schema NAME`; `m1208_app assemble REQUEST [--output RESULT]`; `m1208_app verify RESULT` |
| Schemas | `request`, `output`, `dossier`, `link`, `counter-evidence`, `validation-route`, `claim-ceiling`, `configuration`, `diagnostic` |

## Authority and scope

This implementation is bound to dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
M12-08 lines 4304–4344. The dossier does not freeze endpoint names, wire
media types, catalogue identifiers, or estimator ABI; all public symbols and
package identifiers in this lane remain explicitly provisional. The lane is
metadata-only and does not establish clinical validity, authenticated issuer
authority, calibrated population coverage, or biological truth.

M12-08 accepts caller-declared references only. It never opens the upstream
M12-07 result, proteome, genome/transcriptome, PTM, configuration, or source
artifact content. Identity, lineage, consent, provenance, quality, support,
approved configuration, and intended-use state are checked before typed
conversion. A review-ready chain is emitted only for a closed provisional
architecture family and safe upstream metadata.

## Chain and output semantics

The deterministic reference boundary accepts exactly
`bayesian_graph_baseline_stack`, `network_factor_hybrid`,
`curated_rule_enrichment`, and `orthogonal_consensus_baseline_stack`. A ready
dossier contains one link for each of input, mechanism, counter-evidence,
validation, uncertainty, and claim ceiling; unique counter-evidence records,
a required validation route, explicit claim ceiling, and locked configuration
are all validated. Counter-evidence is represented with its own evidence role
and never erased or relabeled.

Unknown architectures, unsafe upstream support metadata, denied controls,
malformed requests, or unresolved conflicts produce no dossier and no
negative biological finding. They return a typed review-required support
decision, explicit abstention reason, seven non-estimable uncertainty
dimensions, diagnostics, limitations, and `human_review_required=true`.

Every result retains seven uncertainty dimensions (measurement, sampling,
parameter, model-form, identification, support, transport), sensitivity notes,
seven control-decision provenance records, evidence references, canonical
request/result digests, and an explicit claim ceiling. Replay reconstructs the
exact result from the request; tampering is rejected as a safe error.

## Ownership exclusions and recovery

The module emits no KINOPHOS kinase-state claim, generic all-omics fusion,
direct treatment recommendation, identity inference, consent inference,
upstream relabeling, disagreement erasure, or parent-output mutation.
External content traversal is false in every exported schema.

Recovery is deterministic replay plus explicit human review; no overwrite,
persistence, or external side effect is performed by the runtime. Package
evidence records wheel/sdist hashes, member counts, and isolated import
verification. Owner review, synthetic truth, negative-control qualification,
and calibration evidence remain required before ABI promotion.
