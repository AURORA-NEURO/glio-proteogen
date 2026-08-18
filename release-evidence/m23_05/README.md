# M23-05 release evidence

The JSON files in this directory are the frozen local evidence for the
provisional M23-05 lane. `evaluation.json`, `benchmark.json`, and
`coverage.json` are checked by `tools/verify_m2305_release.py`.
`package.json` is populated only after final wheel and sdist verification.
Generated coverage, build, and installation directories are not committed.
The current clean package contains 1,961 wheel members and 4,514 sdist
members; the generated-member audit found no `__pycache__`, `.pyc`, `.m2305-`,
or `coverage_m23_05` paths.
