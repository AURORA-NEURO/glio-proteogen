# M26-03 release evidence

This directory records the reproducible local release checks for the
provisional M26-03 orchestrator. Authority is dossier SHA-256
`sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`,
slice `GLIO-PROTEOGEN_240_Module_Dossier.md:9124-9164`.

The lane is stacked on published M25-08 head `68c73559` because M26-02 has
no published runtime ABI. M26-01/M26-02 are retained as media-only inputs.
Run `py -3.12 tools/verify_m2603_release.py` from the repository root after
building the package to independently validate the manifests.

The current local evidence records 44 focused tests, 95.85% scoped
branch-enabled coverage over 636 statements and 136 branches, 7/7 evaluator
scenarios, 15 adversarial cases, and a 10-iteration benchmark at 2,829,400 ns
mean and 3,126,200 ns p95. The wheel/sdist hashes and isolated import result
are recorded in `package.json`.
