# M23-04 release evidence

This directory contains frozen local evidence for the provisional M23-04
external transport evaluator. Authority is dossier SHA-256
`sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`,
exact slice `GLIO-PROTEOGEN_240_Module_Dossier.md:8088-8128`.

`evaluation.json`, `benchmark.json`, `coverage.json`, and `package.json` are
checked by `tools/verify_m2304_release.py`. Generated coverage, build, and
isolated-install directories are intentionally not committed.

The pinned clean build has no generated archive members: neither the wheel
nor sdist contains `__pycache__`, `.pyc`, `.m2304-`, or `coverage_m23_04`
paths. The wheel and sdist hashes, sizes, and member counts are recorded in
`package.json` and verified against the supplied artifacts.
