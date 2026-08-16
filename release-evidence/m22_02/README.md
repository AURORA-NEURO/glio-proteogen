# M22-02 release evidence

This directory records reproducible local evidence for the provisional
`GLIO-PROTEOGEN-M22-02` synthetic-truth simulation generator. The permitted
authority is dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
slice `GLIO-PROTEOGEN_240_Module_Dossier.md:7640-7680`.

`evaluation.json` records eight executable checks and a frozen fixture digest.
`benchmark.json` records ten timed metadata-only calls against provisional
500,000,000/750,000,000 ns budgets. `coverage.json` records the branch-enabled
scoped coverage gate. `package.json` is populated only after final wheel and
sdist verification. Generated coverage, build, and installation directories
are not source artifacts.
