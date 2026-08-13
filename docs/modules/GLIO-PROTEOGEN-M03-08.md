# M03-08: protein-inference provenance and release packaging

M03-08 closes one authorized C03 protein-inference/ambiguity-control chain into an immutable
release archive and a reproducibility manifest. It packages exact, digest-bound M03-01 through
M03-07 results together with caller-declared software, reference, transformation, quality,
support, and reproducibility metadata. It emits packaging metadata and a signed-release
verification statement only; `complex_activity` remains a downstream target and is never
computed by this module.

## Release boundary

1. Authorize approved configuration, resolved identity/lineage, provenance, consent, quality,
   support, and intended use before traversing upstream results, artifact mappings, or archive
   members.
2. Require one exact full result from every C03 stage M03-01 through M03-07. Each result is
   reconstructed by its public strict contract. The chain must be lineage-consistent,
   internally digest-valid, canonically ordered, and disposition-closed. An unreleasable,
   quarantined, or abstained required stage cannot be packaged as a release.
3. Admit exactly eight declared caller artifacts with unique canonical relative member paths,
   exact byte counts, media types, and SHA-256 digests. Absolute paths, traversal segments,
   aliases, duplicate canonical names, missing members, and undeclared members are rejected.
4. Generate one canonical reproducibility manifest from the closed chain and declared release
   inventory. Its digest is computed before signature verification and is bound into the
   signature statement with its exact release and policy context. The generated verification
   receipt is not part of the signed manifest, preventing circular inclusion.
5. Verify the externally supplied statement through an injected verifier boundary. M03-08
   records the algorithm, key identifier, statement digest, result, and verifier evidence; it
   neither holds signing keys nor authenticates a signer, certificate, or release authority.
6. Build one deterministic ten-member archive: eight caller artifacts, the generated canonical
   manifest, and the generated signature-verification receipt. Archive ordering, timestamps,
   permissions, headers, compression settings, and member bytes are fixed by the contract.
7. Replaying the same authorized request, artifacts, stage objects, and verifier outcome must
   produce complete typed-result equality and byte-identical archive output. Reordering every
   semantically unordered declaration must not change either output.
8. Emit exact member digests, package and manifest digests, stage receipts, signature
   verification, support, uncertainty, provenance, evidence, limitations, recovery guidance,
   and human-review state. The result contract rederives the descriptor's exact canonical-USTAR
   byte size from its member inventory. Only the public verify operation, which receives the
   archive bytes, establishes descriptor-digest/content equality and authenticity status.
   Upstream results and caller bytes remain immutable.

M03-08 is a deterministic release packager, not an event store, registry, scientific model,
anomaly detector, key manager, certificate authority, or generic supply-chain platform. It does
not parse spectra; infer peptides, proteins, groups, isoforms, or proteoforms; recompute quality,
artifact, harmonization, or support decisions; infer identity or consent; calculate complex or
kinase activity; fuse omics; resolve disagreement; recommend treatment; or make a clinical claim.

## Evidence gate

Gate G1 locks eight synthetic scenario groups and exactly 38 cases: canonical release and semantic
reordering; seven stage-specific unreleasable outcomes; cross-chain closure; integrity and archive
safety; signature binding and replay; strict canonical reconstruction; recursive privacy and
ownership; and authorization, recovery, and maximum-shape behavior. Upstream prerequisites are
obtained by executing the public M03-01 through M03-07 entry points; the eval never fabricates
results with `model_construct` or bypasses relational validators.

The representative archive contains exactly ten members: eight synthetic caller artifacts, one
generated manifest, and one generated verification receipt. The deterministic verifier is an
injected fixture seam that establishes control-flow regression only. It is not a cryptographic
primitive and provides no assurance about signer identity, certificates, keys, release authority,
or external evidence truth.

No HTTP endpoint accepts artifact bytes, stage-object mappings, or returns release archives.
HTTP publishes JSON Schema only. Library, service, plugin, and local CLI build/verify interfaces
own the executable binary boundary.

These checks establish deterministic behavior for pinned synthetic bytes and policies only. They
do not establish scientific reproducibility, real-world data integrity, cryptographic assurance,
supply-chain qualification, assay or biological validity, transportability, clinical validity,
or clinical readiness.

See the [module manifest](M03-08.manifest.md),
[evidence inventory](../evidence/M03-08.md), and
[traceability matrix](../traceability/GLIO-PROTEOGEN-M03-08.csv).
