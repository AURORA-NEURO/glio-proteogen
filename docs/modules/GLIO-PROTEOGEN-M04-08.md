# M04-08: proteoform provenance and release packaging

M04-08 closes one authorized C04 proteoform/isoform chain into an immutable release package and
a reproducibility manifest. It owns packaging metadata, provenance closure, exact checksums,
software/reference versions, transformation and quality receipts, support receipts, and a typed
external-signature verification statement. It emits no protein-RNA discordance, proteogenomic
state, proteotype, subtype, kinase activity, fused-omics conclusion, or treatment recommendation.

The authoritative dossier is `GLIO-PROTEOGEN_240_Module_Dossier.md`, SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, lines 1424-1464.
The owner is Bioinformatics, the safety class is S2, and the evidence gate is G1.

## Release boundary

1. Authorize approved configuration, resolved identity/lineage, provenance, granted consent,
   quality, support, and intended use before traversing any stage object, artifact mapping, or
   archive member.
2. Require one exact full result from every C04 stage M04-01 through M04-07. Every result must be
   reconstructed through its public strict contract, remain canonically ordered and digest-valid,
   preserve disagreements, and bind one consistent lineage. An unreleasable stage is quarantined;
   it is never truncated, relabeled, or converted into negative evidence.
3. Admit exactly eight declared caller artifacts: the parent protein-RNA-discordance handoff and
   one canonical result artifact for each M04-01 through M04-07 stage. Member paths, media types,
   byte counts, identifiers, and SHA-256 digests are exact and role-bound.
4. Generate a canonical reproducibility manifest from the closed chain, declared software and
   reference versions, transformation/quality/support receipts, risk-control evidence, reviewer
   sign-off, and rollback evidence. The manifest binds the exact M04-06 transformation-manifest
   and analysis digests when harmonization is accepted.
5. Bind an externally supplied signature statement to the manifest, policy, release identity,
   lineage, intended use, and terminal M04-07 result. M04-08 records an injected verifier outcome;
   it never holds signing keys or authenticates a signer, certificate, key, or release authority.
6. Build one deterministic canonical-USTAR archive: eight caller artifacts, the generated
   reproducibility manifest, and the generated signature-verification receipt. Ordering,
   timestamps, permissions, headers, padding, and member bytes are fixed by the contract.
7. Replaying the same authorized request, exact stage objects, artifact bytes, and verifier outcome
   must produce typed-result equality and byte-identical archive output. A clean environment must
   reproduce the release bit-for-bit; any future numerical tolerance must be declared explicitly
   and cannot weaken archive-byte equality.
8. Emit only the signed release package descriptor, reproducibility manifest, exact support and
   uncertainty receipts, provenance, evidence, limitations, recovery guidance, and human-review
   state. Upstream evidence remains immutable.

## M04-07 dependency hold

The owned M04-08 contract and schema spine is importable before M04-07 freezes, but executable
request validation and runtime build/verify operations are intentionally sealed. A private,
immutable adapter must bind the final M04-07 result identifier convention, media type, disposition
vocabulary, releasable states, direct-upstream receipt, and genuine replay builder. Until that
adapter is installed, the runtime raises `M0408DependencyUnavailableError` before accessing any
upstream object or artifact mapping. No draft M04-07 symbol is part of the public ABI.

## Architecture and claims ceiling

The installed reference boundary is a schema-first deterministic batch packager backed by
canonical object metadata and immutable package bytes. Event-sourced audit integration remains an
alternate deployment architecture; no network-factor or Bayesian model is executed by the package
builder. The fallback is quarantine-first offline validation with mandatory human review.

M04-08 is not an event store, database, scientific model, anomaly detector, key manager,
certificate authority, release authority, or generic supply-chain platform. It does not parse raw
data; infer identity or consent; recompute quality, artifacts, harmonization, support, proteoforms,
or protein-RNA discordance; erase conflict; infer missing facts; own KINOPHOS kinase state; fuse
omics; recommend treatment; or make a clinical claim.

## Acceptance and evidence gate

Gate G1 requires strict schema behavior with zero silent coercions; hard functional invariants;
supported perturbation closure and explicit abstention outside the envelope; declared uncertainty
or narrowed support; zero ownership/consent violations; auditability and recovery; and locked
unit, integration, evaluator, benchmark, traceability, risk-control, data/model/reference,
reviewer-signoff, and rollback evidence. Executable corpus and benchmark claims remain pending the
final M04-07 checkpoint.

See the [module manifest](M04-08.manifest.md),
[evidence inventory](../evidence/M04-08.md), and
[traceability matrix](../traceability/GLIO-PROTEOGEN-M04-08.csv).
