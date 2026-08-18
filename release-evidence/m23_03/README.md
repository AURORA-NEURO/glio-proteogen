# M23-03 release evidence

The JSON files in this directory are the frozen local evidence for the
provisional M23-03 lane. `evaluation.json`, `benchmark.json`, and
`coverage.json` are checked by `tools/verify_m2303_release.py`.
`package.json` is populated only after final wheel and sdist verification.
Generated coverage, build, and installation directories are not committed.

Two builds with `SOURCE_DATE_EPOCH=315532800` were byte-identical. The wheel
is `3,730,449` bytes with `1,945` members and SHA-256
`8c04fcfeb725718290dc1f2658fa97ca97f3aef60a50b84571ce42a948a3fb9a`. The
sdist is `4,284,391` bytes with SHA-256
`202a52874116baedb7c8ce533d0359a0ce5686c473e57f9b1af1759a108fec97`.
