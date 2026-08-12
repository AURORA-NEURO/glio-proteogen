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

All three modules expose strict JSON Schema 2020-12 contracts and typed library, HTTP, and
command-line boundaries. M01-01 and M01-02 additionally provide deterministic append-only
event-chain verification. The database hash chains
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
uv run pytest benchmarks/m01_01_validation.py --benchmark-only --no-cov
uv run pytest benchmarks/m01_02_identity_lineage.py --benchmark-only --no-cov
uv run pytest benchmarks/m01_03_ingestion.py --benchmark-only --no-cov
uv run python -m tools.scan_secrets
```

The `glio-proteogen` command exports each module's contracts and exposes M01-01 register,
evaluate, retrieve, and ledger-verification operations plus M01-02 reconcile, retrieve, and
ledger-verification operations and M01-03 bounded file inspection. For example:

```bash
glio-proteogen export-schema protocol-schema
glio-proteogen identity export-schema request
glio-proteogen identity reconcile request.json --database evidence.sqlite3
glio-proteogen identity verify-ledger --database evidence.sqlite3
glio-proteogen raw export-schema request
glio-proteogen raw inspect variants.vcf --source-id source.variants
```

`glio-proteogen serve` provides the same strict byte-validated operations over HTTP. The
M01-03 inspection boundary is deliberately stateless; it never writes or echoes source content.

All research-facing outputs are research-use-only until their module-specific evidence gate
is independently satisfied. CI and release workflows assemble reproducible candidate evidence;
they never issue reviewer approval or qualify a module.
