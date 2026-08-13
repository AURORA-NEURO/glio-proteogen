# GLIO-PROTEOGEN

GLIO-PROTEOGEN is a clean-room, contract-driven research platform for resolving glioma
biology at the protein, proteoform, complex, and pathway levels while preserving genomic
context, transcript-protein disagreement, uncertainty, provenance, and treatment history.

The repository is being built from an empty history, one bounded module at a time. A module
is considered implemented only when its public contracts, executable behavior, locked
fixtures, adversarial evaluations, microbenchmarks, traceability, and safe-failure behavior
are all present.

See [CLEAN_ROOM.md](CLEAN_ROOM.md) for the construction boundary and
[CONTRIBUTING.md](CONTRIBUTING.md) for the module evidence workflow.

## Scientific boundary

GLIO-PROTEOGEN may emit a proteogenomic state, proteotype, or protein-level subtype object.
It does **not** own kinase-state inference, generic all-omics fusion, or treatment
recommendations. Missing or unsupported evidence is never converted into a negative finding.

## Current modules

- `GLIO-PROTEOGEN-M01-01` — protocol and metadata specification. This vertical slice
  provides versioned protocol schemas, strict metadata conformance, explicit unresolved
  states, compatibility rules, provenance, uncertainty, and deterministic audit events.
- `GLIO-PROTEOGEN-M01-02` — sample identity and lineage reconciliation. This module
  resolves only explicit authority-bound identity assertions, validates the closed lineage
  transition graph, preserves pooling and demultiplexing semantics, and quarantines
  contradictions without relabeling upstream records.
- `GLIO-PROTEOGEN-M01-03` — bounded raw-format ingestion. This module verifies exact
  transport checksums, detects gzip and six open proteomic/genomic formats by content,
  performs structural validation, and emits metadata-only descriptors and typed diagnostics.
- `GLIO-PROTEOGEN-M01-04` — deterministic quality metric computation. This module applies
  assay-declared coverage, completeness, detection-limit, control-material, and sample-context
  calculations while preserving missing and censored evidence as explicit states.
- `GLIO-PROTEOGEN-M01-05` — deterministic artifact and contamination detection. This module
  evaluates seven closed technical-artifact classes, emits typed posteriors and flags, and
  produces a deduplicated exclusion mask without interpreting biological absence.
- `GLIO-PROTEOGEN-M01-06` — deterministic harmonization and normalization. This module applies
  reviewed control-median batch and platform shifts while preserving typed missingness and
  enforcing protected biological direction and rank invariants.
- `GLIO-PROTEOGEN-M01-07` — deterministic support-domain and abstention routing. This module
  evaluates eight closed support dimensions and emits typed abstention reasons and remediation
  paths without converting missing or unsupported evidence into a negative finding.
- `GLIO-PROTEOGEN-M01-08` — deterministic provenance and release packaging. This module
  builds canonical USTAR packages from exact content-addressed artifacts, records reproducibility
  metadata and quality/support decisions, and quarantines packages without a digest-bound external
  signature receipt. It does not authenticate the external signer or validate scientific results.
- `GLIO-PROTEOGEN-M02-01` — deterministic peptide-identification protocol metadata
  conformance. This module validates one pinned schema/profile, controlled terms, units,
  cardinality, conditional applicability, and assay/specimen compatibility while preserving
  unresolved mandatory values as quarantined states. It does not establish ontology completeness,
  assay validity, biological correctness, calibration, or clinical readiness.
- `GLIO-PROTEOGEN-M02-02` — deterministic peptide-identification identity-binding audit.
  This module checks opaque artifact bindings against an immutable M01-02 lineage resolution,
  detects swaps, scoped-token collisions, duplicate content, and cross-patient links, and
  preserves unresolved or unsupported bindings as abstentions without re-solving identity.
- `GLIO-PROTEOGEN-M02-03` — deterministic identification raw-input ingestion. This module
  reuses the shared bounded M01-03 parser, then applies explicit identification roles,
  cardinality, and role-to-format rules without retaining bytes or interpreting biology.
- `GLIO-PROTEOGEN-M02-04` — deterministic peptide-identification quality computation. This
  stateless module computes six closed quality metrics from authorized aggregate observations,
  preserves missing, censored, not-applicable, and unsupported states, and emits only a typed
  quality profile with metric-level provenance. It does not parse raw inputs, rescore
  identifications, estimate new q-values, or interpret biology.
- `GLIO-PROTEOGEN-M02-05` — deterministic peptide-identification artifact detection. This
  stateless module evaluates authorized aggregate QC signals under a pinned rule profile, emits
  configured posteriors and technical flags across seven closed artifact classes, and produces a
  deduplicated exclusion mask without interpreting biological absence or changing upstream data.
- `GLIO-PROTEOGEN-M02-06` — deterministic peptide-identification harmonization. This stateless
  module applies eight ordered control-median adjustments, preserves typed unresolved states,
  enforces M02-05 exclusions, and releases only when technical spread falls while declared
  biological direction and rank controls remain within tolerance.
- `GLIO-PROTEOGEN-M02-07` — deterministic identification support and abstention routing. This
  stateless module reduces genuine M02-04 and M02-06 results to compact receipts, then requires
  one reviewed envelope to admit the complete assay, specimen, disease, quality, completeness,
  platform, reference, and intended-use declaration.
- `GLIO-PROTEOGEN-M02-08` — deterministic identification provenance and release packaging. This
  stateless module closes the exact M02-01 through M02-07 result bytes, one minimal typed parent
  protein-subtype receipt, reviewed software/reference/reproduction evidence, and an externally
  verified signature statement into a canonical ten-member USTAR candidate package.
- `GLIO-PROTEOGEN-M03-01` — deterministic protein-inference protocol and metadata
  conformance. This schema-first module binds one reviewed protocol to exact search-space,
  target-decoy, peptide-eligibility, assignment, protein-grouping, ambiguity-preservation, and
  seven-role complex-activity handoff declarations. It validates those declarations without
  searching spectra, assigning peptides, inferring proteins or complexes, estimating error rates,
  or scoring activity.
- `GLIO-PROTEOGEN-M03-02` — deterministic protein-inference identity and lineage
  reconciliation. This schema-first module binds exact M01-02 and M03-01 results to a closed
  content-addressed artifact DAG spanning peptide-evidence, protein-group, ambiguity, and
  complex-activity-input manifests. It detects swaps, collisions, duplicate assignments,
  cross-patient propagation, malformed derivations, and stale producer bindings while preserving
  categorical copy-number concordance as control evidence only. It never relabels upstream
  identity, infers proteins or identity, consumes raw molecular values, or scores complex activity.
- `GLIO-PROTEOGEN-M03-03` — deterministic protein-inference raw-source admission. This bounded
  module closes genuine M01-02, M03-01, and M03-02 receipts over exact mzML, mzIdentML, strict
  protein-group/ambiguity/bundle JSON, five governed FASTA component roles, PSI-MOD OBO, VCF, and
  GFF3 sources. It verifies transport and decoded integrity, structure, cross-references, builds,
  controlled vocabularies, and units without retaining raw bytes or inferring proteins or activity.
- `GLIO-PROTEOGEN-M03-04` — deterministic protein-inference quality computation. This stateless
  module evaluates eight exact rational metrics from one authorized aggregate fact ledger, preserves
  censored, missing, not-applicable, and unsupported states, and binds every result to the selected
  assay profile, controls, references, and compact M03-03 projection. That caller-declared projection
  proves internal content consistency, not independent M03-03 execution or issuer authenticity.
- `GLIO-PROTEOGEN-M03-05` — deterministic protein-inference artifact and contamination detection.
  This stateless module evaluates eight locked technical signals across six role-closed evidence
  unit kinds and emits categorical evidence scores, artifact states, contamination flags, and a
  retain/review/exclude mask. Its evidence scores are explicitly not calibrated probabilities.
- `GLIO-PROTEOGEN-M03-06` — deterministic protein-inference support harmonization. This stateless
  module applies eight exact lower-median fixed-point technical stages to retained support units,
  verifies held-out residual reduction plus direction, rank, and ambiguity invariants, and emits
  replayable transformations without abundance, probability, identity, or activity inference.
- `GLIO-PROTEOGEN-M03-07` — deterministic protein-inference support and abstention routing. This
  stateless module rederives compact M03-04/M03-06 receipts from their full strict results, then
  requires one reviewed envelope to admit the complete eight-dimension declaration without
  combining partial matches or inferring protein, proteoform, activity, or clinical meaning.
- `GLIO-PROTEOGEN-M03-08` — deterministic protein-inference provenance and release packaging.
  This stateless module closes genuine strict M03-01 through M03-07 results over eight exact
  caller artifacts, emits a canonical ten-member USTAR archive, and verifies externally supplied
  statements through an injected boundary without signing, key custody, or release authority.
- `GLIO-PROTEOGEN-M04-01` — deterministic proteoform/isoform protocol conformance. This stateless
  module closes a reviewed reference bundle, coordinate conventions, evidence eligibility,
  isoform discrimination, modification localization, quantification, and discordance handoff
  declaration without inferring proteoforms, discordance, activity, subtype, or treatment.
- `GLIO-PROTEOGEN-M04-02` — deterministic proteoform/isoform identity and lineage
  reconciliation. This stateless module closes genuine full M01-02 and M04-01 results over seven
  physical kinds, five opaque artifact roles, and one four-role assembly while retaining swaps,
  collisions, duplicates, cross-patient links, and non-observed evidence without identity repair
  or biological inference.

The twenty-five published module slices and the M04-02 release candidate expose strict JSON Schema
2020-12 contracts through HTTP and command-line schema routes, plus typed library and
module-specific command boundaries. M01-01 and M01-02 additionally provide deterministic
append-only event-chain verification. The database hash chains are integrity evidence, not
signatures or standalone external trust anchors. M01-02 accepts
only scoped opaque identity tokens and privacy-minimized concordance summaries; raw direct
identifiers, genotypes, reads, and molecular measurements are outside its public and persisted
outputs.

## Development

```bash
uv sync
uv run ruff check .
uv run mypy src
uv run pytest
uv run python -m evals.m01_01.run
uv run python -m evals.m01_02.run
uv run python -m evals.m01_03.run
uv run python -m evals.m01_04.run
uv run python -m evals.m01_05.run
uv run python -m evals.m01_06.run
uv run python -m evals.m01_07.run
uv run python -m evals.m01_08.run
uv run python -m evals.m02_01.run
uv run python -m evals.m02_02.run
uv run python -m evals.m02_03.run
uv run python -m evals.m02_04.run
uv run python -m evals.m02_05.run
uv run python -m evals.m02_06.run
uv run python -m evals.m02_07.run
uv run python -m evals.m02_08.run
uv run python -m evals.m03_01.run
uv run python -m evals.m03_02.run
uv run python -m evals.m03_03.run
uv run python -m evals.m03_04.run
uv run python -m evals.m03_05.run
uv run python -m evals.m03_06.run
uv run python -m evals.m03_07.run
uv run python -m evals.m03_08.run
uv run python -m evals.m04_01.run
uv run python -m evals.m04_02.run
uv run pytest benchmarks/m01_01_validation.py --benchmark-only --no-cov
uv run pytest benchmarks/m01_02_identity_lineage.py --benchmark-only --no-cov
uv run pytest benchmarks/m01_03_ingestion.py --benchmark-only --no-cov
uv run pytest benchmarks/m01_04_quality_metrics.py --benchmark-only --no-cov
uv run pytest benchmarks/m01_05_artifact_detection.py --benchmark-only --no-cov
uv run pytest benchmarks/m01_06_harmonization.py --benchmark-only --no-cov
uv run pytest benchmarks/m01_07_support_routing.py --benchmark-only --no-cov
uv run pytest benchmarks/m01_08_release_packaging.py --benchmark-only --no-cov
uv run pytest benchmarks/m02_01_metadata_validation.py --benchmark-only --no-cov
uv run pytest benchmarks/m02_02_identity_bindings.py --benchmark-only --no-cov
uv run pytest benchmarks/m02_03_identification_ingestion.py --benchmark-only --no-cov
uv run pytest benchmarks/m02_04_quality_metrics.py --benchmark-only --no-cov
uv run pytest benchmarks/m02_05_artifact_detection.py --benchmark-only --no-cov
uv run pytest benchmarks/m02_06_harmonization.py --benchmark-only --no-cov
uv run pytest benchmarks/m02_07_support_router.py --benchmark-only --no-cov
uv run pytest benchmarks/m02_08_release_packaging.py --benchmark-only --no-cov
uv run pytest benchmarks/m03_01_protocol_metadata.py --benchmark-only --no-cov
uv run python -m evals.m03_02.benchmark
uv run python -m evals.m03_03.benchmark
uv run python -m evals.m03_04.benchmark
uv run python -m evals.m03_05.benchmark
uv run python -m evals.m03_06.benchmark
uv run python -m evals.m03_07.benchmark
uv run python -m evals.m03_08.benchmark
uv run python -m evals.m04_01.benchmark
uv run python -m evals.m04_02.benchmark
uv run python -m tools.scan_secrets
```

The `glio-proteogen` command exports each module's contracts and exposes M01-01 register,
evaluate, retrieve, and ledger-verification operations plus M01-02 reconcile, retrieve, and
ledger-verification operations, M01-03 bounded file inspection, M01-04 quality computation,
M01-05 artifact detection, M01-06 technical harmonization, M01-07 support routing, M01-08
directory-backed release package build and verification, and M02-01 peptide-identification
metadata conformance, M02-02 immutable identity-binding audit, and M02-03 directory-backed
identification raw-input ingestion, M02-04 stateless identification-quality computation, M02-05
stateless identification-artifact detection, M02-06 identification harmonization, M02-07
identification support routing, and M02-08 directory-backed identification release packaging and
verification, plus M03-01 stateless protein-inference protocol conformance and M03-02 stateless
protein-inference artifact identity-lineage reconciliation, plus M03-03 bounded, directory-backed
protein-inference raw-source admission, M03-04 metadata-only quality computation, M03-05
categorical artifact detection over an authorized evidence ledger, and M03-06 fixed-point support
harmonization, M03-07 protein-inference support and abstention routing, M03-08 local,
directory-backed protein-inference release packaging and verification, and M04-01 stateless
proteoform/isoform protocol conformance, plus M04-02 stateless proteoform/isoform identity and
lineage reconciliation.
For example:

```bash
glio-proteogen export-schema protocol-schema
glio-proteogen identity export-schema request
glio-proteogen identity reconcile request.json --database evidence.sqlite3
glio-proteogen identity verify-ledger --database evidence.sqlite3
glio-proteogen raw export-schema request
glio-proteogen raw inspect variants.vcf --source-id source.variants
glio-proteogen quality export-schema request
glio-proteogen quality compute quality-request.json
glio-proteogen artifact export-schema request
glio-proteogen artifact detect artifact-request.json
glio-proteogen harmonize export-schema request
glio-proteogen harmonize run harmonization-request.json
glio-proteogen support export-schema request
glio-proteogen support route support-request.json
glio-proteogen release export-schema request
glio-proteogen release build release-request.json release-source --output release.tar
glio-proteogen release verify release-result.json release.tar
glio-proteogen identification export-schema request
glio-proteogen identification validate-metadata conformance-request.json
glio-proteogen binding export-schema request
glio-proteogen binding audit identity-binding-request.json
glio-proteogen identification-raw export-schema request
glio-proteogen identification-raw ingest ingestion-request.json source-directory
glio-proteogen identification-quality export-schema request
glio-proteogen identification-quality compute identification-quality-request.json
glio-proteogen identification-artifacts export-schema request
glio-proteogen identification-artifacts detect identification-artifact-request.json
glio-proteogen identification-harmonization export-schema request
glio-proteogen identification-harmonization harmonize identification-harmonization-request.json
glio-proteogen identification-support export-schema request
glio-proteogen identification-support route identification-support-request.json
glio-proteogen identification-release export-schema request
glio-proteogen identification-release build identification-release-request.json release-source --output identification-release.tar
glio-proteogen identification-release verify identification-release-result.json identification-release.tar
glio-proteogen protein-inference-protocol export-schema request
glio-proteogen protein-inference-protocol validate protein-inference-protocol-request.json
glio-proteogen protein-inference-lineage export-schema request
glio-proteogen protein-inference-lineage reconcile protein-inference-lineage-request.json
glio-proteogen protein-inference-raw export-schema request
glio-proteogen protein-inference-raw ingest protein-inference-raw-request.json source-directory
glio-proteogen protein-inference-quality export-schema request
glio-proteogen protein-inference-quality compute protein-inference-quality-request.json
glio-proteogen protein-inference-artifacts export-schema request
glio-proteogen protein-inference-artifacts detect protein-inference-artifact-request.json
glio-proteogen protein-inference-harmonization export-schema request
glio-proteogen protein-inference-harmonization harmonize protein-inference-harmonization-request.json
glio-proteogen protein-inference-support export-schema request
glio-proteogen protein-inference-support route protein-inference-support-request.json
glio-proteogen protein-inference-release export-schema request
glio-proteogen protein-inference-release build protein-inference-release-request.json release-source --output protein-inference-release.tar
glio-proteogen protein-inference-release verify protein-inference-release-result.json protein-inference-release.tar
glio-proteogen proteoform-protocol export-schema request
glio-proteogen proteoform-protocol validate proteoform-protocol-request.json
glio-proteogen proteoform-lineage export-schema request
glio-proteogen proteoform-lineage reconcile proteoform-lineage-request.json
```

`glio-proteogen serve` provides the strict byte-validated HTTP operations and all module schema
routes. M01-08 intentionally keeps artifact bytes at its library and directory-backed CLI boundary;
it does not invent an HTTP upload protocol. M01-03 inspection, M01-04 quality computation, M01-05
artifact detection, M01-06 harmonization, M01-07 support routing, M01-08 release packaging, and
M02-01 metadata conformance are stateless. M01-08 publishes package bytes only for a released
result; quarantined results remain metadata-only. M02-02 is also stateless and consumes only an
already-issued M01-02 resolution plus opaque content-addressed binding claims.
M02-03 is also stateless: byte content stays at the library or safe directory-backed CLI
boundary, while its result contains only digests, format metadata, and typed diagnostics.
M02-04 is stateless and consumes only authorized aggregate observations and fixed thresholds;
it emits a typed quality profile and does not retain raw spectra, PSMs, or biological claims.
M02-05 is stateless and consumes only authorized aggregate identification-QC signals plus a pinned
profile, policy, and explicit rules. It emits typed technical flags and a target-level exclusion
mask; it does not parse raw assay inputs, repair measurements, infer protein subtypes, or retain
raw spectra or peptide rows.
M02-06 is stateless and consumes only the exact M02-01 through M02-05 receipts plus typed aggregate
abundance observations. It emits a harmonized analysis object and auditable eight-stage
transformation manifest; it does not parse assay files, impute missing evidence, alter upstream
artifacts, or make subtype, kinase-state, treatment, or clinical claims.
M02-07 is stateless and consumes only compact, digest-bound M02-04/M02-06 receipts plus reviewed
support envelopes and typed declarations. It emits support-domain assessments, abstention reasons,
and reviewed remediation codes; it does not copy harmonized values, combine partial envelope
matches, infer biology, or make treatment or clinical claims.
M02-08 is stateless and closes exact, separately supplied M02-01 through M02-07 JSON result bytes
against their typed objects, artifact declarations, issued digests, dispositions, lineage receipts,
and cross-stage identity bindings. Its manifest is signed without including the generated signature
verification receipt, avoiding a circular statement. The HTTP surface is schema-only. The CLI has
no built-in verifier: a build therefore returns typed quarantine metadata and writes no archive,
while verification can establish canonical structure and content but not authenticity. Positive
release remains a library/service/plugin operation with an explicitly injected verifier. M02-08
does not inspect the parent subtype artifact for biological meaning, own signing keys, authenticate
release authority, infer kinase state, fuse omics, or make treatment or clinical claims.
M03-01 is stateless and validates only a caller-declared, content-bound protein-inference protocol
and reviewed profile. Its conformance receipt preserves search-space-relative uniqueness,
shared/razor evidence restrictions, indistinguishable group members, and the exact downstream
handoff semantics. It does not authenticate issuers or references, inspect observations, run
protein inference, estimate false-discovery rates, infer complex activity, or make treatment or
clinical claims.
M03-02 is stateless and consumes exact, self-validating M01-02 and M03-01 results plus opaque,
content-addressed artifact claims, a reviewed lineage policy, and categorical copy-number
concordance receipts. It preserves the physical lineage graph separately from the artifact DAG,
quarantines swaps, collisions, duplicate assignments, cross-patient propagation, and producer
drift, and abstains when governed upstream identity or concordance evidence is unresolved. It does
not repair or infer identity, inspect peptide sequences or protein accessions, consume raw
copy-number or abundance values, infer proteins or complexes, score activity, fuse omics, or make
treatment or clinical claims.
M03-03 is stateless and binds genuine M01-02, M03-01, and M03-02 receipts to one bounded,
content-addressed raw-source capsule. Its library surface consumes bytes or read-once streams; its
CLI maps exact safe source identifiers to regular non-reparse files beneath one directory. The HTTP
surface exports schemas only and deliberately has no raw-ingestion POST route. It validates
transport, decompression, structural references, search-space/PTM closure, and build/CV/unit
coherence without retaining source bytes, assigning peptides, inferring proteins or complexes,
scoring activity, or making treatment or clinical claims.
M03-04 is stateless and consumes one authorization-checked, caller-declared compact M03-03 receipt,
one aggregate fact ledger, and one reviewed assay-quality policy. It computes exact integer-rational
source completeness, peptide assignment, ambiguity, proteoform discrimination, detection support,
competition closure, control recovery, and sample-context coherence metrics while retaining typed
unresolved states. The compact receipt and ledger establish self-consistency under their digests;
they do not independently attest that M03-03 executed or authenticate an issuer. M03-04 does not
parse raw sources, traverse peptide rows, redo protein inference, score complex activity, infer a
proteotype, or make treatment or clinical claims.
M03-05 is stateless and consumes one authorization-checked compact M03-04 quality receipt, one
content-addressed role-compatible artifact ledger, and one reviewed detector policy. It reduces
exact integer supporting/evaluated counts into categorical evidence scores and technical masks;
it does not parse raw sources, assign proteins, estimate calibrated probabilities, score complex
activity, authenticate an external issuer, or make treatment or clinical claims.
M03-06 is stateless and consumes the exact compact M03-05 artifact projection plus a bounded,
content-addressed support ledger and reviewed eight-stage profile. It derives signed lower-median
fixed-point shifts, applies them sequentially only to retained observed units, and replays held-out
technical residuals plus direction, rank, and ambiguity-fraction invariants. It preserves typed
missingness and the artifact firewall; it does not estimate abundance or calibrated probability,
infer protein, proteoform, complex activity, or kinase state, authenticate an external issuer, or
make treatment or clinical claims.
M03-07 is stateless and consumes full strict M03-04 and M03-06 results alongside compact receipts
rederived from those exact results solely to prove projection closure. It routes the complete
assay, specimen, disease-class, quality, completeness, platform, reference, and intended-use
declaration against one reviewed joint envelope, preserving missing/unknown states and emitting
only support or typed abstention with governed remediation. It does not reinterpret or mutate
upstream results, combine partial envelopes, infer protein, proteoform, complex activity, or kinase
state, authenticate an external issuer, or make treatment or clinical claims.
M03-08 is stateless and consumes exact canonical bytes plus separately supplied strict full
M03-01 through M03-07 result objects. It closes stage identity, predecessor, quality, artifact,
harmonization, support, intended-use, and parent bindings before signature verification; then it
emits eight caller members plus one generated manifest and one verification receipt in canonical
USTAR form. The result contract rederives descriptor byte size, while the verify API establishes
descriptor digest/content equality and authenticity against supplied bytes. M03-08 does not sign,
hold keys, authenticate a signer, establish release authority, mutate upstream evidence, infer
protein or activity, or make treatment or clinical claims.
M04-01 is stateless and validates one content-bound proteoform/isoform protocol declaration against
one reviewed conformance profile. It preserves exact reference, coordinate, eligibility,
discrimination, localization, quantification, unresolved-state, and protein-RNA-discordance
handoff semantics. It does not inspect assay observations, infer proteoforms or discordance,
localize modifications, fuse omics, score kinase activity, emit subtypes, or recommend treatment.
M04-02 is stateless and consumes exact full M01-02 and M04-01 results plus opaque, role-compatible
artifact claims and one reviewed derivation policy. It preserves the seven-kind physical lineage
separately from the five-role artifact graph, retains duplicate content, and quarantines swaps,
collisions, cross-patient links, and producer drift while abstaining on non-observed evidence. It
does not repair or infer identity, inspect artifact bytes, execute CN-to-protein regression, infer
protein, proteoform, discordance, or kinase state, fuse omics, or make treatment or clinical claims.

All research-facing outputs are research-use-only until their module-specific evidence gate
is independently satisfied. CI and release workflows assemble reproducible candidate evidence;
they never issue reviewer approval or qualify a module.
