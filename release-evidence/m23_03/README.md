# M23-03 release evidence

The JSON files in this directory are the frozen local evidence for the
provisional M23-03 lane. `evaluation.json`, `benchmark.json`, and
`coverage.json` are checked by `tools/verify_m2303_release.py`.
`package.json` is populated only after final wheel and sdist verification.
Generated coverage, build, and installation directories are not committed.

Two builds with `SOURCE_DATE_EPOCH=315532800` were byte-identical. The wheel
is `3,857,065` bytes with `1,990` members and SHA-256
`bb894bfcaa4f22677ad54ac55dddafc4ed119ed6d70e851598dc9dcd348c65bf`. The
sdist is `4,508,639` bytes with `4,624` members and SHA-256
`318b402ef6c803f0251c235fd26b7a15dcf85efb09c3b04e3af016bed864285e`.
