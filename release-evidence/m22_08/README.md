# M22-08 release evidence

This directory contains frozen local evidence for the provisional M22-08
evidence gate and release adjudicator. The authority is dossier SHA-256
`sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`,
exact slice `GLIO-PROTEOGEN_240_Module_Dossier.md:7904-7944`.

`evaluation.json`, `benchmark.json`, `coverage.json`, and `package.json` are
checked by `tools/verify_m2208_release.py`. Generated coverage, build, and
isolated-install directories are intentionally not committed.

Two builds with `SOURCE_DATE_EPOCH=315532800` were byte-identical. The wheel
is `3,857,365` bytes with `1,990` members and SHA-256
`4efd815407a5c4acb6a59a2d31c3b85484b632407116060cb472591ef78bd39b`; the sdist
is `4,511,890` bytes with `4,624` members and SHA-256
`3517782efbee4303fb5617084b87ea0088fc0e815aa646fd070b9f57d387e16c`.
