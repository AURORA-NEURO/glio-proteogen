# M23-03 release evidence

The JSON files in this directory are the frozen local evidence for the
provisional M23-03 lane. `evaluation.json`, `benchmark.json`, and
`coverage.json` are checked by `tools/verify_m2303_release.py`.
`package.json` is populated only after final wheel and sdist verification.
Generated coverage, build, and installation directories are not committed.

Two builds with `SOURCE_DATE_EPOCH=315532800` were byte-identical. The wheel
is `3,857,112` bytes with `1,990` members and SHA-256
`864e44692be5a52692abf4df331f14bd60b0cca45ea8ceead66f518097b48ff5`. The
sdist is `4,505,464` bytes with `4,623` members and SHA-256
`a038a8e2836d3d4b9e0e5b8ed6b9201bd0909df57d87c1b3179a8697c78548db`.
