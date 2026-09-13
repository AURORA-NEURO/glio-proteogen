# GLIO-PROTEOGEN project status

Status date: 2026-08-29

## Evidence-based inventory

Project status is derived from files in the current checkout. The verifier no
longer turns the historical delivery grid into a single completion percentage:

```bash
uv run python tools/verify_project_status.py
```

The deterministic JSON report inventories these surfaces separately:

- contract packages;
- `engine.py` implementations across the complete `glio_proteogen` source tree,
  with module service and plugin counts retained alongside them;
- central adapters and module API/CLI adapters;
- test files grouped by suite;
- standard and alternate evaluation entry points, evaluation benchmarks, and
  repository benchmark entry points under `benchmarks/`; and
- structured and narrative evidence files across `evidence/`,
  `release-evidence/`, `docs/evidence/`, `docs/release-evidence/`, and research
  evidence under `docs/research/`.

Each category includes a count, byte total, a SHA-256 digest over its sorted
repository-relative paths, and a second SHA-256 digest binding every path to the
bytes stored there. `inventory_digest` binds the complete report, making both
source-tree changes and in-place content mutations visible without pretending
that every artifact has the same scientific or engineering maturity.

## Per-module validation closure

Inventory is not treated as validation. A second fail-closed verifier binds
each discovered contract/module pair to importable Draft 2020-12 schemas,
runtime structure, a fresh-process evaluator, benchmarks, direct tests, and
repository evidence:

```bash
uv run python tools/verify_module_validation.py
uv run python tools/verify_module_validation.py \
  --run-evaluators --evaluator-timeout-seconds 300 \
  --run-benchmarks --benchmark-timeout-seconds 300
```

The current discovery closes exactly 214 contract packages against 214 unique
implementation directories and 214 evaluator entry points. Static closure is
reported separately from evaluator execution. The 37 governed/mature and 177
provisional labels remain maturity metadata; a passing evaluator does not
promote a provisional ABI or scientific claim.

The current complete evaluator-and-benchmark receipt validates all 214 modules
with zero failures and is summarized in
[`docs/evidence/module-validation.md`](evidence/module-validation.md). Its
machine-readable companion is `module-validation.json`; both bind the exact
source inventory rather than the historical 28×8 planning grid.

CI executes all evaluators and benchmarks in eight deterministic sorted
round-robin shards. The complete pytest job supplies JUnit XML and
branch-enabled Cobertura evidence to the same verifier, which records per-module
test execution and governed source coverage without replacing the
repository-wide 95% coverage gate or the 100% gates on newly introduced research
contracts, engine, service, and API paths. Reports include content-bound scope,
repository, profile, evidence, and validation digests. They do not authenticate
the machine that produced them.

## Planning convention and known gaps

The 28-module by 8-cell grid (224 cells) is retained only as a planning
assumption. It is explicitly marked `is_completion_claim: false` in the machine
report.

Known provisional source IDs remain:

`M23_06`, `M24_01`, `M27_01`, `M28_01`, `M28_02`, `M28_03`, `M28_05`,
`M28_06`, `M28_07`, and `M28_08`.

The verifier fails if a package appears under one of those IDs without the
provisional list first being reviewed. This prevents a newly created directory
from silently being interpreted as a resolved ABI or completed research claim.

## Verification posture

- CI validates workflow structure and rejects duplicate YAML mapping keys before
  running quality checks.
- CI validates every discovered module in deterministic evaluator-and-benchmark
  shards and binds the full-suite JUnit and coverage receipts back to the same
  214-module source inventory.
- Existing governed v1 contracts retain their contract, property, integration,
  replay, and deployment suites.
- Research algorithms and research evidence are reported independently from the
  governed module matrix; their presence does not promote them to clinical use.
- The backend image installs the locked production dependency graph and CI emits
  a CycloneDX package inventory plus build-input checksums with the container
  smoke-test evidence.
- Linked Compose deployment runs both the non-root API and workbench UI with
  read-only root filesystems and health-gated startup.

Passing tests or having a complete artifact inventory is engineering evidence,
not evidence of clinical validity, treatment utility, or regulatory readiness.
