# M06 depth hardening

This evidence package audits M06-01 through M06-08 on the current M26 base
`77fb1ce6537161b529c53084fa8e27a9c18f021a`. The ABI remains provisional; this
change does not add protein, proteoform, isoform, glioma-specific, treatment, or
kinase inference. It hardens the existing validated-token capability boundary
and restores the established global API/CLI route parity for M06-01, M06-03,
M06-04, and M06-06.

## Closure

- Full M06 contract, lifecycle, evaluator, tooling, interface, and adversarial selection: **306 passed**.
- Capability adversarial matrix: **8 passed**, covering cross-plugin reuse, forged tokens, and post-issuance request mutation.
- Ruff check and format, compileall, and strict MyPy on all 10 changed source files: clean.
- Scoped branch-enabled coverage over the eight M06 module trees: **1,857/1,920 statements; 345/374 branches; 95.9895% combined coverage**. The pure branch ratio is 92.246%; both values are recorded so the combined gate is not mistaken for branch-only coverage.
- Evaluators M06-01 through M06-08: all passed; evaluator details are in `release-evidence/m06_depth_hardening_evaluation.json`.
- Locked benchmarks: all passed; timings and budgets are in `release-evidence/m06_depth_hardening_benchmark.json`.
- Two pinned wheel/sdist builds were byte-identical; isolated wheel import probe passed. Hashes are in `release-evidence/m06_depth_hardening_package.json`.

## Change size

Compared with the current M26 base, the branch contributes **832 additions, 32 deletions, net +800 Python LOC across 11 files**. The resulting tracked repository contains **627,502 Python LOC across 3,692 files**.

## Reproduction

```text
$tests = rg --files tests | Where-Object { $_ -match 'm06.*\\.py$' }
uv run pytest -q -o addopts='' --no-cov $tests
uv run coverage run --branch -m pytest -q -o addopts='' --no-cov $tests
uv run coverage report --include='src/glio_proteogen/modules/c06_estimation/m06_03_mature_baseline_estimator/*,src/glio_proteogen/modules/c06_protein_abundance/m06_0[1-8]_*/*'
uv build --wheel --sdist --out-dir dist-m06-a
uv build --wheel --sdist --out-dir dist-m06-b
```
