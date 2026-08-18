# M23-02 release evidence

This directory records current-main evidence for the provisional synthetic
truth and simulation generator. Authority is dossier SHA-256
`sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`,
exact slice `GLIO-PROTEOGEN_240_Module_Dossier.md:8000-8040`.

`evaluation.json`, `benchmark.json`, `coverage.json`, and `package.json` are
checked by `tools/verify_m2302_release.py`. The generator is metadata-only:
fixture labels are not measurements, and M23-01 remains an opaque,
caller-declared input with no service import or content traversal.

Build hashes and isolated import evidence are refreshed after the final
current-main source state. Generated build, coverage, and installation
directories are intentionally excluded from the repository.

Two builds with `SOURCE_DATE_EPOCH=315532800` were byte-identical. The wheel
is `3,713,185` bytes with `1,935` members and SHA-256
`64713c7bd5b675552c7f9bd817d0283b51582efbdd6c8c81fa448b4f6bc350c2`. The
sdist is `4,268,359` bytes with SHA-256
`3d22f8a34a8ed25298337a7e32d6e9051c97144b108d90653865243365f18353`.
