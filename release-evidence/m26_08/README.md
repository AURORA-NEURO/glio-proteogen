# M26-08 release evidence

The evidence in this directory is for the provisional retirement, archival and
knowledge-transfer service beneath the protein subtype parent.

- Authority: dossier SHA-256 `0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact slice `GLIO-PROTEOGEN_240_Module_Dossier.md:9344-9384`.
- Evaluator: 10/10 frozen scenarios; fixture digest is recorded in `evaluation.json`.
- Benchmark: 10 calls, mean 1,976,310 ns, p95 2,856,100 ns; budgets 500,000,000 / 750,000,000 ns.
- Package: wheel and sdist hashes are recorded in `package.json`; isolated import passed.
- Generated package/install directories were removed before the release commit; `package.json` records this closure.
- GitHub Actions may fail before job steps because of repository account billing/spending-limit provisioning; that is external CI state and does not change local gate results.
