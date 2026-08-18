# M23-01 release evidence

This directory contains frozen local evidence for the provisional M23-01
reference-truth and benchmark curator. The authority is dossier SHA-256
`sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`,
exact slice `GLIO-PROTEOGEN_240_Module_Dossier.md:7956-7996`.

`evaluation.json`, `benchmark.json`, `coverage.json`, and `package.json` are
checked by `tools/verify_m2301_release.py`. Generated coverage, build, and
isolated-install directories are intentionally not committed.

The current-base release artifacts were produced twice with
`SOURCE_DATE_EPOCH=315532800` and were byte-identical. The wheel is
`3,702,048` bytes with SHA-256
`0b7e5557602a8771bab8660f406893ed01af945509d9035dc0bba314b4aad339` and
`1,929` archive members. The source distribution is `4,248,155` bytes with
SHA-256 `0cf976ea3cb8362a1915fa02c1522a1b655c61be53559dcdea90bd506d34f920`.
The wheel was installed into an isolated Python 3.12 environment and the
M23-01 contract import check passed.
