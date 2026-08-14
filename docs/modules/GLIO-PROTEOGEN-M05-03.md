# GLIO-PROTEOGEN-M05-03 - raw input ingestion

M05-03 validates four canonical raw-input manifest documents beneath the C05 PTM-localization
inference. It consumes the exact full M05-02 identity-lineage resolution and a separate in-memory
mapping of four roles to immutable bytes, then emits only validated manifest objects and typed
parse diagnostics supporting the parent `variant_peptide` workflow. It never opens an
external scientific content artifact, parses spectra or scientific rows, computes a quality
metric, executes a model, or infers identity, consent, protein, ptm_localization, PTM, discordance,
kinase activity, subtype, proteotype, treatment, or a clinical conclusion.

## Locked behavior

1. Authorize approved configuration, resolved identity/lineage, provenance, consent, quality,
   support, and intended use before traversing the request, embedded lineage result, policy,
   artifacts, byte mapping, or nested values. Each denial fails closed with zero governed
   traversal. Built-in dict access ignores hostile subclass overrides; ordinary exceptions fail
   closed, while `BaseException` propagates unchanged.
2. Bind the operation `ingest_ptm_localization_raw_inputs`, contract version 1.0.0, and one identical
   opaque request identifier across the request and context. Revalidate the exact full public
   M05-02 `PtmLocalizationIdentityLineageResolution`; a compact receipt or re-signed substitute is not
   accepted.
3. Bind context identity to the lineage identity digest, quality evidence to the M05-02 result
   digest, support evidence to the M05-02 receipt digest, intended-use evidence to the lineage
   receipt, and approved-configuration evidence to the M05-03 configuration digest. Close
   upstream completion and policy-review chronology before M05-03 completion.
4. Generate the four canonical documents before M05-02 construction. Bind their manifest
   references into a genuine public M05-02 request, execute genuine public M01-02, M05-01, and
   M05-02 operations, then construct M05-03. Handwritten upstream outputs are prohibited.
5. If the replayed M05-02 result is quarantined, emit typed M05-03 quarantine with
   `upstream_lineage_quarantined` and zero artifact traversal. If it is abstained, emit typed
   abstention with `upstream_lineage_abstained` and zero artifact traversal. Only a reconciled
   result permits access to the artifact-byte mapping.
6. Require the exact four roles `mass_spectrometry_proteome`, `genome`, `transcriptome`, and
   `ptm_annotations`. Project them exactly to the four corresponding M05-02 manifest claims.
   Missing or extra mapping entries, arbitrary mappings, non-`bytes` values, and `bytes`
   subclasses reject before parsing.
7. Require each submitted M05-02 manifest reference, claim identifier, declared size, content
   digest, media type, document type, format, format version, and parser version to close exactly.
   Structural and integrity failures reject; diagnostics never mask them.
8. Cap the canonical request at 4,194,304 bytes, each document at 8,388,608 bytes, and the exact
   four-document aggregate at 33,554,432 bytes. Enforce byte caps before JSON parsing or hashing
   where applicable. The declared record count may range from zero through
   9,223,372,036,854,775,807 and is never used for allocation.
9. Parse strict duplicate-free JSON and require its bytes to be the installed canonical encoding.
   Reject malformed JSON, duplicate keys, unknown fields, scalar coercion, noncanonical bytes,
   and role/document-type mismatch. Canonical semantic reordering yields complete result equality.
10. Use between four and 32 approved parser profiles, with all four roles covered. Each profile
    fixes role, format, format version, parser version, media type, maximum document bytes, and
    evidence. The ingester validates declarations; it does not establish parser or assay truth.
11. Embed exactly one strict document type for each role. Common metadata binds identity,
   protocol, reference bundle, assay/specimen policy, intended use, assay protocol, specimen
    processing, unit definition, content reference, declared record count, evidence,
    completeness, assay support, and parent quality. Role-specific controlled metadata remains
    typed; no raw rows or external scientific payload enter the result.
12. Record only the exact 17 diagnostic codes. `duplicate_content_retained` records without
    deduplication; upstream abstention and artifact non-evaluability abstain; every installed
    semantic mismatch quarantines. Quarantine takes precedence over abstention, which takes
    precedence over record-only diagnostics. Emit at most one diagnostic per code and role,
    canonically aggregating every comparison basis into its evidence digest, so every valid input
    remains within the installed 60-diagnostic result cap.
13. Preserve duplicate content, validated documents, manifest references, content references,
    and upstream objects exactly. Never deduplicate, relabel, repair, rewrite, mutate, promote, or
    infer a negative from missing, indeterminate, unsupported, or redacted evidence.
14. Emit only `validated`, `quarantined`, or `abstained`. Validated results are supported,
    quarantined results require review, and abstained results are unsupported. Review is required
    exactly when the disposition is not validated.
15. Safe upstream quarantine or abstention returns exactly seven local control-evidence records,
    one policy record, and four parser-profile records: 12 total. A reconciled request additionally
    returns four manifest-reference and four content-reference records, for 20 through 48 total.
    Embedded upstream evidence remains inside the replayed lineage result.
16. Emit all seven uncertainty dimensions as `not_estimable` and exactly three limitations:
    `deterministic_raw_manifest_validation_only`,
    `external_content_and_authority_not_authenticated`, and
    `no_protein_discordance_or_clinical_inference`.
17. Fully rederive validated inputs, diagnostics, disposition, receipt, support, uncertainty,
    provenance, evidence, limitations, review, completion time, and result digest when validating
    a result. Re-signed upstream, receipt, diagnostic, input, provenance, evidence, or result
    regions reject.
18. Use opaque local identifiers only in the namespaces `request`, `actor`, `decision`, `policy`,
    `parser`, `input`, `evidence`, and `reviewer`, each followed by exactly 64 lowercase
    hexadecimal characters. Result and activity identifiers derive from the canonical request
    digest as `result.m0503.*` and `activity.m0503.*`.
19. Export exactly 12 JSON Schema 2020-12 contracts: request, output, policy, parser-profile,
    input-artifact, proteome-document, genome-document, transcriptome-document, ptm-document,
    validated-input, diagnostic, and receipt. Expose schema HTTP GET only. Deliberately expose no
    HTTP execution POST because raw-byte canonicalization and duplicate-key behavior belong to the
    explicit bytes boundary.
20. Expose CLI `ptm_localization-raw export-schema NAME` and
    `ptm_localization-raw ingest REQUEST SOURCE --output RESULT`. `SOURCE` must contain exactly four
    named regular files and no extras: `mass-spectrometry-proteome.json`, `genome.json`,
    `transcriptome.json`, and `ptm-annotations.json`. Symlinks, junctions, reparse points,
    missing entries, and nonregular files reject. Snapshot each input once. The output must not
    exist or be a symlink,
    and publication is an atomic new-file operation with no reread or partial output.
21. Recover append-only. A corrected request may identify a superseded result digest, but it never
    overwrites source bytes or a prior result. Critical discrepancy, novel/OOD state, support
    override, claim promotion, release exception, or unresolved biological conflict remains
    external human-review work.

Every receipt and result retains `variant_peptide` only as parent context and sets all
authority flags false. M05-03 emits no parent output, proteogenomic state, proteotype,
protein-level subtype, identity, consent, protein, ptm_localization, kinase state, CN-to-protein
regression, all-omics fusion, treatment recommendation, upstream mutation, or model execution.

## Architecture and authority boundary

The dossier lists an event-sourced quality service and schema-first batch alternative with a
protein interaction GNN, plus a quarantine-first deterministic pipeline and protein-complex
graph fallback. Gate G0 installs only the deterministic schema-first
manifest-validation boundary and quarantine-first failure semantics. It installs no scientific
graph, GNN, anomaly learner, estimator, event log, database, object
store, registry, or mutable persistence. Architecture and model names remain manifest
declarations, not executed methods.

The separate four-role byte mapping contains only canonical manifest objects. A document may
carry a content reference to an external scientific artifact, but M05-03 never opens, fetches,
streams, parses, authenticates, or interprets that artifact. Checksums and caller-declared review
records make local replay deterministic and tamper-evident under the installed rules; they do not
prove scientific correctness, issuer authority, identity, assay execution, or reference truth.

## Evidence gate

Gate G0 locks exactly 72 unique synthetic, non-clinical cases in eight groups allocated
7/9/8/8/8/7/7/18: canonical ingestion; mapping integrity and byte caps; version, unit, and
reference validation; completeness, assay, and parent quality; upstream closure and safe failure;
diagnostics and nonmutation; evidence, uncertainty, and authority; and strict authorization,
interface, privacy, ordering, and replay boundaries. Declared and executed case sets must match
exactly.

The representative benchmark prepares genuine M01-02, M05-01, and M05-02 results and four modest
canonical documents outside measurement. After one untimed warm-up, it measures exactly 25
public `ingest_ptm_localization_raw_inputs` calls. Mean latency must be at most 500 milliseconds and p95
at most 750 milliseconds. The 8 MiB and 32 MiB capacity shapes belong to eval, not the
representative benchmark. These limits are software regression tripwires, not scientific,
biological, transportability, calibration, or clinical evidence.

See the [module manifest](M05-03.manifest.md),
[evidence inventory](../evidence/M05-03.md), and
[traceability matrix](../traceability/GLIO-PROTEOGEN-M05-03.csv).
