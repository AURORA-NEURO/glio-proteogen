# M03-03: protein-inference raw-source admission

M03-03 admits one bounded, content-addressed source capsule beneath C03 protein inference and
ambiguity control. It reconstructs the exact public M01-02 -> M03-01 -> M03-02 chain, verifies the
governed source mapping before opening a file, reads each admitted regular file once, and validates
transport integrity, compression, format structure, internal references, cross-source bindings,
and governed build/CV/unit context. It emits only an immutable admission capsule and typed parse
diagnostics that support a later `complex_activity` workflow.

## Admission-capsule boundary

1. Authorize approved configuration, identity/lineage, provenance, consent, quality, support, and
   intended use before resolving a source mapping or touching the filesystem. Each denial control
   has a hostile-mapping oracle whose traversal and source-read counts must remain zero.
2. Close over genuine, self-validating public M01-02, M03-01, and M03-02 results. Embedded results,
   their derived digests, request bindings, the entire M03-02 claim set, identity graph, protocol,
   and search-space identity must agree. A valid M03-02 quarantine or abstention propagates before
   source I/O; it is not reclassified as malformed input.
3. Accept only a complete request-declared mapping of exact portable basenames beneath one governed
   source directory. A source name is never interpreted as a path. Directories, absolute names,
   traversal segments, alternate data streams, symlinks, junctions, and other reparse points fail
   closed. The complete mapping and capacity are validated before any file is opened, and every
   admitted regular file is read exactly once.
4. Support the v1 profiles needed by this boundary: spectra as mzML; peptide evidence as
   mzIdentML; protein-group, ambiguity, and complex-activity-input-bundle manifests as strict JSON;
   canonical, decoy, conditional-isoform, variant, and contaminant search-space components as
   distinct FASTA sources; PTM vocabulary as PSI-MOD OBO; variants as VCF; and transcript
   annotations as GFF3. V1 deliberately omits mzTab and mzTab-M.
5. Detect gzip from transport magic bytes, not a filename suffix. Bind both transported and decoded
   length/digest declarations. Corrupt streams, checksum mismatch, raw-size mismatch, decoded-size
   mismatch, unsupported formats, unsupported versions, malformed structures, and dangling
   references remain separate typed diagnostics.
6. Parse enough structure to prove the declared profile and reference closure, never to issue a
   biological result. mzML and mzIdentML identifiers and references, JSON object keys and declared
   references, FASTA component records, PSI-MOD identifiers, VCF headers/records, and GFF3
   directives/records are checked within explicit caps. mzIdentML requires a unique XML-ID index,
   identifier-safe values for every XML attribute ending in `_ref`, resolution of every such
   reference against that document-wide index, and complete reviewed container shape; FASTA
   component keys are nonempty, identifier-safe, and unique. Duplicate JSON keys and silent scalar
   coercions are forbidden.
7. Bind all five exact M03-01 FASTA component roles and the PTM ontology digest. Missing,
   unexpected, or swapped components fail closed. Matching basenames, display labels, versions, or
   descriptions cannot override a role or content-digest mismatch.
8. Bind the bundle without a digest cycle. The bundle bytes declare the digest of a source manifest
   formed from every other admitted source; the request's complete source index separately binds
   the bundle bytes. The admission capsule carries both bindings and the exact M03-02 parent
   receipt without modifying either object.
9. Check search-space build, VCF assembly, GFF3 assembly, controlled-vocabulary, and unit context at
   their governed boundaries. A mismatch is reviewable and quarantined. Required missing or
   explicitly unsupported context produces typed abstention and is never converted into a negative
   finding.
10. Apply deterministic failure precedence: authorization, source mapping, transport integrity,
    decompression, format structure, cross-reference closure, then governed context. Later
    disagreements that can be established safely remain retained; precedence determines outcome,
    not deletion of evidence or selection of biological truth.
11. Canonicalize semantically unordered declarations so equivalent ordering produces a completely
    equal result. Typed, dictionary, and strict-JSON request surfaces, and bytes versus read-once
    streams, must agree. Derived values and nested content are revalidated; recomputing an outer
    digest cannot legitimize forged inner content.
12. Expose raw ingestion through the public library operation, service, plugin, and CLI. The HTTP
    adapter exposes installed schema GET routes only: raw bytes and a source directory are
    deliberately not accepted through a POST route. A correction creates a new immutable capsule
    with explicit supersession provenance; a prior capsule is never edited.
13. Emit no direct patient identifier, raw identity token, peptide sequence, protein-presence or
    protein-absence assertion, protein-inference result, abundance, complex-activity score, subtype,
    proteotype, kinase state, fused-omics conclusion, treatment recommendation, or clinical
    decision.

M03-03 is a deterministic, bounded admission service, not a search engine, spectrum-identification
engine, peptide-to-protein inference algorithm, protein-group resolver, ambiguity model, abundance
estimator, pathway or complex-activity model, mutable registry, file-transfer service, LIMS, or
clinical decision-support system. Structural acceptance means that supplied bytes satisfy the
locked admission profile and declared bindings; it does not authenticate their issuer, attest that
a laboratory step occurred, or establish biological truth.

## Evidence gate

Gate G0 contains exactly 79 executable cases in eight synthetic, non-clinical groups: genuine
upstream closure and the canonical admission capsule; role/format and cross-reference parsing;
M03-01 search-space and PTM closure; M03-02 identity-graph and source-manifest binding; build/CV/unit
coherence; typed failure precedence and disagreement retention; authorization, strictness,
capacity, and filesystem safety; and canonicalization, privacy, interfaces, recovery, and the
representative benchmark.

The executable chain must call public M01-02, feed its exact result to public M03-01, feed both
genuine results into public M03-02, create real source bytes and digests, construct the non-circular
bundle/source-manifest binding, and only then call public M03-03. Handwritten upstream result
envelopes and prevalidated parse outputs are forbidden. The representative benchmark constructs
the upstream chain and source capsule outside its timed region, then times only the public M03-03
operation. Its broad ceiling is a deterministic regression tripwire, not evidence of assay,
biological, transport, or clinical performance.

See the [module manifest](M03-03.manifest.md),
[evidence inventory](../evidence/M03-03.md), and
[traceability matrix](../traceability/GLIO-PROTEOGEN-M03-03.csv).
