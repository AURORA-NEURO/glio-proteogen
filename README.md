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

## Current module

`GLIO-PROTEOGEN-M01-01` — protocol and metadata specification.

The first vertical slice provides versioned protocol schemas, strict metadata conformance,
explicit unresolved states, compatibility rules, provenance, uncertainty, deterministic
audit events, a typed API, and a command-line interface.

## Development

```bash
uv sync
uv run ruff check .
uv run mypy src
uv run pytest
uv run python -m evals.m01_01.run
uv run pytest benchmarks/m01_01_validation.py --benchmark-only --no-cov
uv run python -m tools.scan_secrets
```

The `glio-proteogen` command exports the versioned JSON Schema 2020-12 contracts and exposes
M01-01 register, evaluate, retrieve, and ledger-verification operations. `glio-proteogen serve`
provides the same strict byte-validated operations over HTTP. Both surfaces use the same service,
canonical digest rules, and append-only event ledger.

All research-facing outputs are research-use-only until their module-specific evidence gate
is independently satisfied.
