# M21-05 release evidence

This directory records reproducible local evidence for the provisional
`GLIO-PROTEOGEN-M21-05` subgroup equity evaluator. Authority is dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
slice `GLIO-PROTEOGEN_240_Module_Dossier.md:7412-7452`.

`evaluation.json` records one nominal and eight adversarial executable
scenarios plus fixture digests. `benchmark.json` records twenty-five timed
calls and provisional 500,000,000/750,000,000 ns budgets. `coverage.json` is
branch-enabled scoped coverage for M21-05 contracts and runtime/interfaces.
`package.json` is populated after the final wheel and sdist are built and
verified. The release verifier checks all manifests, artifact sizes and
hashes, wheel member count, and isolated import. Generated coverage, build,
and installation directories are not committed.
