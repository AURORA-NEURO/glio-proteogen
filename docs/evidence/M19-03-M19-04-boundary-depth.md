# M19-03/M19-04 boundary-depth release evidence

This current-main hardening lane is intentionally limited to caller-claim and
intended-use safety boundaries. It does not infer proteins, proteoforms,
isoforms, glioma-specific biology, kinase activity, treatment, identity, or
consent from caller text.

## Authority and dependency

- M19-03 authority: dossier SHA-256
  `0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`,
  exact slice `GLIO-PROTEOGEN_240_Module_Dossier.md:6604-6644`.
- M19-04 authority: the same dossier SHA, exact slice
  `GLIO-PROTEOGEN_240_Module_Dossier.md:6648-6688`.
- Base: `8cc38ba1`; this branch is a current-main safety hardening lane, not a
  replacement for either provisional ABI.

## Implemented depth

- M19-03 exposes one authoritative prohibited-claim vocabulary in contract
  metadata and scans configuration, aggregate values, source ownership/claims,
  uncertainty notes, evidence claims, and disagreement text before emitting an
  integrated object. Any prohibited caller claim produces typed abstention
  with ownership-unclear evidence.
- M19-04 exposes its prohibited vocabulary in contract metadata and scans
  audience, claim ceiling, rationale, registration evidence, and display
  evidence. Blocked disclosures remain visibly abstained and cannot become a
  bounded object. Declared `prohibited_interpretations` remain policy boundary
  declarations, not caller claims, so supported fixtures remain valid.
- API, CLI, service, and plugin paths are regression-tested for exact parity;
  JSON Schema metadata uses JSON arrays consistently across direct, API, and CLI
  exports.

## Gates

- Focused M19-03/M19-04 contract, runtime, coverage, interface, and evaluation
  suite: **84 passed**.
- Evaluators: M19-03 **8/8 scenarios and 8/8 adversarial**, M19-04 **9/9
  scenarios and 8/8 adversarial**.
- Scoped branch-enabled coverage: **98.36567926455567% combined** across 16
  M19-03/M19-04 contract and runtime files (819 statements, 9 missed; 160
  branches, 7 missed). The ordinary coverage report rounds this to 98%.
- Strict MyPy: **31 files clean**. Ruff check and format: clean. Compileall:
  clean.
- 25-iteration benchmark: M19-03 mean **1,307,060 ns**, p95 **1,822,100 ns**;
  M19-04 mean **2,739,208 ns**, p95 **3,336,000 ns**. Both are within the
  provisional 500,000,000/750,000,000 ns budgets.
- Package builds A/B were byte-identical. Wheel: **3,669,477 bytes**, SHA-256
  `2488a5f0e0abc56ebc949d712346e2848308f73d1fc36e07e01c390ab3a28635`.
  Sdist: **4,212,150 bytes**, SHA-256
  `fb5ebefa15544483101db743a43af2fc97d46d8c09e92a5b4f7bbb33fcc9e3fa`.
  Isolated wheel import passed.

## Python LOC

Against base `8cc38ba1`, the branch changes **13 Python files**, with **311
additions / 25 deletions / +286 net LOC**. The current tracked repository total
is **545,778 Python LOC across 3,696 files**.
