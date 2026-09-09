# GLIO-PROTEOGEN-M11-04 module manifest

| Property | Provisional locked value |
| --- | --- |
| Module | GLIO-PROTEOGEN-M11-04 |
| Responsibility | Network, state, or mechanism inference beneath Protein-native subtype inference |
| Owner / safety / gate | Clinical science / S2 / G2 |
| Parent target | `variant_peptide` (context only; `emits_parent=false`) |
| Version / ABI | `0.1.0-provisional`; dossier behavioral brief only, pending owner confirmation |
| Operation | `infer_variant_peptide_mechanism` |
| Input boundary | Opaque M11-01 hypothesis result reference, locked configuration, model/calibration references, source/counter-evidence references, identity, provenance, consent, quality, support, intended-use controls |
| Output ceiling | Posterior or state estimate, assumptions, alternatives, counter-evidence, typed uncertainty, support, provenance, evidence, limitations, and explicit abstention |
| Selected runtime | Deterministic caller-declared posterior/state grammar with replay-bound canonical digests |
| API | `GET /v1/m11-04/schema/{name}`; `POST /v1/modules/M11-04/mechanism`; `POST /v1/modules/M11-04/verify` |
| CLI | `m1104_app export-schema NAME`; `m1104_app infer REQUEST [--output RESULT]`; `m1104_app verify RESULT` |
| Schemas | `request`, `output`, `estimate`, `configuration`, `finding` |

## Authority and scope

This implementation is bound to dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
M11-04 lines 3768–3825. The dossier does not freeze endpoint names, wire media
types, catalog identifiers, or model ABI; every public symbol and package
identifier in this lane is marked provisional. The implementation does not
claim a clinical mechanism, authenticated issuer, or scientific truth.

M11-04 accepts only caller-declared references. It never opens raw proteome,
genome/transcriptome, PTM, model, calibration, or upstream result content. The
M11-01 result is bound by media type and digest as an opaque artifact. Identity,
lineage, consent, provenance, support, quality, approved configuration, and
intended-use state are validated before any method or artifact traversal.

## Method and output semantics

The selected deterministic reference boundary accepts exactly:

* `posterior:<mechanism-id>:<label>:<probability>:<lower>:<upper>` with finite values in `[0,1]` and ordered bounds;
* `state:<mechanism-id>:<label>:<active|inactive|present|absent|upregulated|downregulated|stable>`; or
* `abstain:<reason>` for explicit safe failure.

Unknown grammar, malformed bounds, unsupported state, missing controls, and
missing counter-evidence produce an abstained result with no estimate, typed
unsupported support, finding, human-review requirement, seven non-estimable
uncertainty dimensions, and machine-readable limitations. Unsupported or
missing evidence is never converted to a negative mechanism finding.

Every inferred estimate retains at least one assumption, alternative, and
counter-evidence reference. Every result carries seven uncertainty dimensions
(measurement, sampling, parameter, model-form, identification, support,
transport), sensitivity notes, seven control-decision provenance records,
canonical request digest, and canonical result digest. Replay reconstructs the
result from the exact request; tampered result or request content is rejected.

## Ownership exclusions

The module emits no kinase activity (KINOPHOS ownership), generic all-omics
fusion, direct treatment recommendation, identity inference, consent
inference, upstream relabeling, disagreement erasure, or parent-output
mutation. External content traversal is false in every exported schema.

## Evidence and recovery

The locked synthetic fixture has seven cases covering posterior inference, state
inference, explicit and unknown-method abstention, invalid bounds, replay and
tamper, and authorization denial. Recovery is deterministic replay plus
explicit human review; no overwrite, persistence, or external side effect is
performed by the runtime. Package evidence records wheel/sdist hashes,
member counts, and isolated import verification.
