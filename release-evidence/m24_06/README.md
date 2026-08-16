# M24-06 release evidence

These JSON files freeze the local evidence for the provisional M24-06
robustness shift/OOD challenge. `evaluation.json`, `benchmark.json`, and
`coverage.json` are checked by `tools/verify_m2406_release.py`.
`package.json` is populated only after final wheel/sdist and isolated-import
verification. Generated coverage, build, and installation directories are
not committed.
