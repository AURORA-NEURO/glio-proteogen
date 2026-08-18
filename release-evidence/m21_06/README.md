# M21-06 release evidence

This directory records reproducible local evidence for the provisional
`GLIO-PROTEOGEN-M21-06` robustness, shift, and OOD challenge boundary. The
permitted authority is dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
slice `GLIO-PROTEOGEN_240_Module_Dossier.md:7456-7496`.

`evaluation.json` records twelve executable checks and frozen fixture
request/result digests. `benchmark.json` records ten timed metadata-only
calls against provisional 500,000,000/750,000,000 ns budgets.
`coverage.json` records the branch-enabled scoped coverage gate.
`package.json` is populated only after the final wheel and sdist are built and
verified. Generated coverage, build, and installation directories are not
source artifacts.
