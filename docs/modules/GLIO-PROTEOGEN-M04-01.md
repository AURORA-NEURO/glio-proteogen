# GLIO-PROTEOGEN-M04-01 - proteoform/isoform protocol and metadata specification

M04-01 validates one pinned protocol declaring how already-governed mass-spectrometry proteome,
genome/transcriptome, and PTM-annotation inputs may later support proteoform/isoform work. It owns
the controlled vocabulary, mandatory metadata, units, assay and specimen versions, cardinality,
compatibility, unresolved-state semantics, and a closed downstream handoff beneath C04
Proteoform/isoform inference. It emits only a versioned protocol schema, conformance profile, and
compact receipt supporting the parent `protein_rna_discordance` workflow. It evaluates
declarations only: it does not inspect measurements, identify a proteoform or isoform, localize a
PTM, quantify abundance, compute protein-RNA discordance, or make any biological inference.

## Locked behavior

1. Authorize approved configuration, resolved identity/lineage, provenance, consent, quality,
   support, and intended use before traversing the protocol, profile, references, policies, or
   caller evidence. Each denied control fails closed before governed traversal, including when a
   downstream value is a hostile mapping or `dict` subclass.
2. Bind the request, context, protocol, reviewed profile, and emitted receipt to one exact module
   identity, operation `evaluate_proteoform_protocol`, semantic version, and content-derived
   identifier set. A split request/context identifier, stale schema pin, duplicate reviewed entry,
   or caller-authored derived value is rejected rather than repaired.
3. Require exactly 11 protocol sections: `applicability`, `identity`, `metadata_versions`,
   `reference_bundle`, `coordinate_mapping`, `evidence_eligibility`, `isoform_discrimination`,
   `modification_localization`, `quantification`, `unresolved_semantics`, and
   `discordance_handoff`. Missing, duplicate, unknown, or extra sections are structural failures.
4. Require all seven installed identity keys—`patient_id`, `specimen_id`, `aliquot_id`,
   `section_id`, `analyte_id`, `run_id`, and `derived_object_id`—and bind every declared artifact
   to the same identity/lineage. Missing identity is never inferred, and an artifact identity
   conflict is rejected before conformance evaluation.
5. Close one reference bundle over an exact canonical protein reference, isoform reference,
   genome reference, transcript reference, PTM-annotation reference, coordinate profile, and
   their content digests. The coordinate policy declares separate genome, transcript, and protein
   conventions, an exact `coordinate_mapping_version`, explicit conversion, required reference-
   allele and sequence-residue validation, explicit insertion/deletion handling, and unresolved
   mismatch handling. Reference cardinality is a separate closed declaration. Missing mandatory
   references, non-closing reference cardinality, cross-artifact conflicts, and impossible
   coordinate relations are rejected; a reviewed-domain coordinate-profile mismatch produces a
   typed quarantine.
6. Validate evidence eligibility as protocol metadata only. Bottom-up unique evidence must be
   unique relative to the exact bundle; top-down evidence must declare an intact-proteoform rule;
   splice-junction evidence requires the bound transcript reference; sequence-variant evidence
   requires the bound genome reference; shared evidence cannot be promoted to a member claim; and
   a profile-controlled minimum of independent discriminators is required. Passing these rules
   does not assert that any evidence or molecular entity was observed.
7. Validate modification-localization policy without localizing a modification. Require the exact
   reviewed threshold and unit, residue validation, explicit labile-modification handling, and
   preservation of ambiguous site sets. `unlocalized`, `ambiguous`, and `absent` are distinct;
   an unlocalized declaration can never be converted to absence.
8. Validate only reviewed quantification-method and normalization pairs. Require explicit
   observation semantics before numeric zero may be used, and preserve `missing`, `not_detected`,
   and `below_lod` as distinct states. No accepted pair establishes abundance accuracy,
   comparability, calibration, or biological discordance.
9. Require all ten installed unresolved states as exact, non-overlapping declarations: `missing`,
   `unknown`, `unsupported`, `conflicting`, `not_applicable`, `redacted`, `not_detected`,
   `below_detection_limit`, `isoform_ambiguous`, and `site_ambiguous`. Omission, aliasing, or
   conflation is rejected. Unsupported, missing, unresolved, censored, or non-observed evidence
   never becomes a negative biological finding.
10. Emit exactly eight digest-bound `discordance_handoff` roles: `reference_bundle`,
    `transcript_protein_mapping`, `coordinate_mapping`, `isoform_discrimination`,
    `modification_localization`, `quantification_units`, `unresolved_states`, and `provenance`.
    The handoff carries only protocol conformance metadata into the exact parent
    `protein_rna_discordance` context. It cannot contain a discordance result,
    proteoform/isoform/PTM call, abundance result, proteotype, protein-level subtype, kinase
    activity, generic all-omics fusion, treatment recommendation, or clinical decision.
11. Emit findings only in the closed `pass` and `fail` states, conformance status only as
    `conformant` or `nonconformant`, and disposition only as `conformant` or `quarantined`.
    Reviewed-domain mismatches quarantine; malformed structure, relational contradiction,
    ownership overreach, and forgery are rejected.
12. Canonicalize every semantically set-like collection before deriving field-owned digests.
    Semantic reordering yields the same normalized request, request digest, result, result digest,
    receipt, and receipt digest. Duplicate entries remain invalid and are never hidden by
    canonicalization.
13. Enforce the installed collection ceilings: four approved applicabilities, 64 reference
    bundles, 32 entries in each approved version/vocabulary collection, eight coordinate profiles,
    16 quantification pairs, five evidence classes, three terms in the profile's approved labile-
    modification-handling allowlist, five approved isoform-discriminator classes, and a scalar
    ceiling of 16 required independent
    discriminators, plus exactly 11 sections, seven identity keys, ten unresolved-state
    declarations, eight handoff roles, 21 result-evidence entries, and three exact limitations.
    Reference-cardinality ceilings are 10,000,000 genes, 250,000,000 transcripts, 250,000,000
    canonical protein sequences, 250,000,000 isoform sequences, 500,000,000 transcript-protein
    edges, and 10,000,000 modification terms. The maximum useful profile conforms; each first
    excess is rejected. Reject a canonical request larger than 4,194,304 bytes before evaluation.
14. Accept strict immutable JSON only. Reject duplicate JSON keys, scalar coercion, non-finite
    numbers, unknown fields or controlled terms, missing required members, stale derived values,
    non-allowlisted artifact media types, contradictory nesting, and re-signed result, finding,
    receipt, evidence, or provenance forgery.
15. Use opaque content-derived identifiers recursively in only the namespaces `request`, `actor`,
    `decision`, `schema`, `profile`, `bundle`, `vocabulary`, `reviewer`, and `evidence`, followed by
    `.` and exactly 64 lowercase hexadecimal characters. Do not reflect a biological canary,
    sequence, accession, direct identifier, or caller-injected biological assertion through a
    finding, evidence item, provenance record, receipt, or limitation.
16. Publish exactly 13 JSON Schema 2020-12 documents: `request`, `output`, `protocol`, `profile`,
    `reference-bundle`, `reference-cardinality`, `coordinate-policy`,
    `evidence-eligibility-policy`, `isoform-discrimination-policy`,
    `modification-localization-policy`, `quantification-policy`, `discordance-handoff`, and
    `receipt`.
17. Expose one public operation, `evaluate_proteoform_protocol`, with HTTP
    `POST /v1/modules/M04-01/protocol-conformance`, schema HTTP
    `GET /v1/contracts/M04-01/{name}/schema`, and CLI
    `proteoform-protocol validate REQUEST` and `proteoform-protocol export-schema NAME`
    boundaries. All interfaces strictly reconstruct
    the same request and return complete typed-result parity.
18. Recover append-only. Correction produces a new immutable request and result with exact
    supersession provenance; it never edits, deletes, silently promotes, or relabels the prior
    result. Critical discrepancy, novel/OOD state, support override, claim promotion, release
    exception, or unresolved biological conflict remains external human-review work.

## Architecture and authority boundary

The dossier names event-sourced quality, schema-first batch, and quarantine-first designs, plus
PCA/ICA and multi-block PLS alternatives. This G0 implementation selects the deterministic
schema-first conformance boundary. The model names are retained in the manifest as explicitly
non-executed architecture declarations: M04-01 loads no weights, fits no model, scores no record,
and makes no anomaly, latent-factor, calibration, or biological claim. External control,
reference, review, and digest assertions remain caller-declared and content-bound; M04-01 does not
authenticate an issuer, prove reference truth, confer approval authority, or mutate an upstream
artifact.

The exclusive technology outputs named by the dossier—proteogenomic state, proteotype, and a
protein-level subtype object—belong to governed downstream work, not to this protocol validator.
KINOPHOS retains exclusive kinase-state ownership. Generic all-omics fusion and direct treatment
recommendation are prohibited.

## Evidence gate

Gate G0 locks exactly 46 unique synthetic, non-clinical cases in eight groups allocated
`6/6/6/5/5/9/3/6`: reference-bundle and coordinate closure; evidence and isoform compatibility;
PTM-localization semantics; quantification and discordance handoff; identity and metadata
versions; strict construction, installed caps, canonicalization, and forgery; authorization and
append-only recovery; and privacy/result ownership. The executable corpus uses public strict
constructors and only the public evaluator. Structural rejection, typed quarantine, conformant
results, zero-traversal denial, digest equality, immutable recovery, and recursive ownership are
all explicit oracles.

The representative benchmark performs untimed maximum-conformant-profile construction and one
untimed warm-up, then times exactly 25 public `evaluate_proteoform_protocol` calls. Mean latency
must be at most two seconds and p95 at most three seconds. These limits are regression tripwires,
not evidence of assay performance, model accuracy, uncertainty calibration, biological validity,
transportability, or clinical readiness.

See the [module manifest](M04-01.manifest.md),
[evidence inventory](../evidence/M04-01.md), and
[traceability matrix](../traceability/GLIO-PROTEOGEN-M04-01.csv).
