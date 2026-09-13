# Repository-wide module validation evidence

This receipt records engineering validation of every module discovered in the current checkout. It
does not promote provisional modules, establish clinical validity, or replace module-specific
scientific evidence.

## Bound source and profile

- Upstream source commit: `b0339c55e1efad82997caefe8ffe030389f0e23e`
- Development branch: `feature/research-evidence-graph`
- Validation schema: `glio-module-validation/1.2.0`
- Validation profile: `module-evaluator-benchmark-closure/1.0.0`
- Profile digest: `sha256:1290f1496f144b99333b1cac529d18cd419a9fa24709f8496e95fd9eef0a0e42`
- Repository-content digest: `sha256:04513c89607b5ebd667f7fa31ec0a7c4e2b8286d75bde23da1a4ba0baa7dfd17`
- Validation digest: `sha256:ca8232d69fca1725a8e762a5b9c5fd73d260954e8df62287afd9ed727a88625c`
- Machine receipt: `module-validation.json`

## Result

| Gate | Result |
| --- | ---: |
| Contract packages discovered | 214 |
| Implementation directories discovered | 214 |
| Closed contract/implementation pairs | 214 |
| Governed modules | 37 |
| Provisional modules | 177 |
| Fresh-process evaluators passed | 214 / 214 |
| Fresh-process benchmark entrypoints passed | 214 / 214 |
| Modules with bound passing JUnit evidence | 214 / 214 |
| Modules with complete governed-source coverage records | 214 / 214 |
| Failed modules | 0 |

The input JUnit document contains 12,349 cases: 10,897 bind uniquely to a module through stable
`file` or `classname` provenance and 1,452 shared or non-module cases remain conservatively
unassociated. Test names do not establish ownership. The JUnit evidence digest is
`sha256:af202531c84398268c8347cc165a683b05617185098ffb25347a983d9bf2527e`.

Coverage binds exactly 2,064 repository source files. Absolute paths outside the repository are
ignored, while duplicate aliases inside the repository fail closed. The coverage evidence digest
is `sha256:6b6d730b9e760c1e3b0411069753ebf837f11dc71529db17ba1d1f7336eb07e5`.

## Execution record

The complete test-and-coverage run completed with 12,332 passing tests, 17 explicitly skipped
historical-artifact tests, no failures, and 96.24% aggregate branch-aware coverage. The Cobertura
totals were 142,465 / 146,404 lines and 28,151 / 30,878 branch arcs. After tightening JUnit and
coverage provenance parsing, its focused regression suite completed 89 / 89 tests with strict MyPy
and Ruff clean. M02-05's unchanged 24-result workload was repeated in eight fresh processes after
its cross-run ceiling repair; all runs passed under the documented 750 ms mean ceiling.

The final combined receipt was produced with:

```bash
uv run python tools/verify_module_validation.py \
  --run-evaluators --run-benchmarks \
  --evaluator-timeout-seconds 300 --benchmark-timeout-seconds 300 \
  --junit-xml .tmp-module-tests-final.junit.xml \
  --coverage-report coverage.xml \
  --format json --output module-validation.json
```

Every module result binds static closure, evaluator execution, benchmark execution, JUnit evidence,
and coverage evidence independently. A passing result is an engineering claim over the recorded
source and fixtures only; it is not a scientific, clinical, regulatory, or release-authority claim.
