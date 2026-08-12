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

All eleven modules expose strict JSON Schema 2020-12 contracts through HTTP and command-line
schema routes, plus typed library and module-specific command boundaries. M01-01 and M01-02
additionally provide deterministic append-only event-chain verification. The database hash chains
are integrity evidence, not signatures or standalone external trust anchors. M01-02 accepts
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
uv run python -m tools.scan_secrets
```

The `glio-proteogen` command exports each module's contracts and exposes M01-01 register,
evaluate, retrieve, and ledger-verification operations plus M01-02 reconcile, retrieve, and
ledger-verification operations, M01-03 bounded file inspection, M01-04 quality computation,
M01-05 artifact detection, M01-06 technical harmonization, M01-07 support routing, M01-08
directory-backed release package build and verification, and M02-01 peptide-identification
metadata conformance, M02-02 immutable identity-binding audit, and M02-03 directory-backed
identification raw-input ingestion.
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

All research-facing outputs are research-use-only until their module-specific evidence gate
is independently satisfied. CI and release workflows assemble reproducible candidate evidence;
they never issue reviewer approval or qualify a module.
