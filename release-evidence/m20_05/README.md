# M20-05 release evidence

This directory records reproducible local evidence for the provisional
`GLIO-PROTEOGEN-M20-05` workflow presentation service. The authority is dossier
SHA-256 `0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`,
exact slice `GLIO-PROTEOGEN_240_Module_Dossier.md:7052-7092`.

`evaluation.json` records eight executable scenarios and the frozen fixture
request/result digests. `benchmark.json` records ten timed calls and the
provisional 500,000,000/750,000,000 ns budgets. `coverage.json` is branch-
enabled scoped coverage for M20-05 contracts, runtime/interfaces, and evals.
`package.json` is populated only after the final wheel and sdist are built and
verified. The release verifier checks all four manifests, artifact sizes and
hashes, wheel member count, and isolated import. Generated coverage, build, and
installation directories are not committed as source artifacts.
