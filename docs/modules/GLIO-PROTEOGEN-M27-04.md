# GLIO-PROTEOGEN-M27-04 module manifest

| Property | Provisional value |
| --- | --- |
| Module | `GLIO-PROTEOGEN-M27-04` |
| Title | API / SDK / CLI gateway |
| Parent | `complex activity` |
| Owner / safety / gate | Clinical science / S3 / G2 |
| Authority | Dossier SHA `0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, lines `9528-9568` |
| ABI status | `0.1.0-provisional`; behavioral brief only; pending owner confirmation |
| Public operation | `publish_complex_activity_access_surface` |
| Input | Caller-declared typed operations, authorization, idempotency, async jobs, compatibility, errors, audit, source artifacts, and seven controls |
| Output ceiling | Access metadata surface or explicit abstention; typed findings; provenance; support; seven not-estimable uncertainty dimensions; limitations; review state |
| Protocols | API, SDK, CLI; each enabled explicitly in configuration |
| Fallback | Offline signed release bundles are declared as fallback metadata only; no signing or authentication is performed here |
| Model count | Zero; no external model, registry, object store, event log, or scientific-file traversal |
| Prohibited | Complex-activity biology claims, kinase activity, generic all-omics fusion, treatment, identity inference, consent inference |

The runtime is stateless and deterministic. All records are caller-declared and internally bound by
canonical digests; provenance and control records preserve source identity and evidence without
asserting their authenticity. Unsupported, unresolved, unauthorized, or tampered material is
retained as typed review/abstention state rather than converted into a negative claim.

Authorization records are graph-closed: each record must reference a declared operation and its
scope must exactly match that operation's declared authorization scope before publication.

The source manifest must also include the exact mass-spectrometry/proteome, genome/transcriptome,
and PTM input references declared by the request. This keeps gateway provenance bound to every
named input rather than only to an arbitrary caller-selected evidence subset.
