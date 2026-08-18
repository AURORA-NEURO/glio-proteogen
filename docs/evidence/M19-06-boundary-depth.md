# M19-06 boundary-depth evidence

This current-main hardening closes a caller-controlled claims boundary in the
M19-06 reviewer discrepancy and adjudication queue. It preserves the
provisional ABI and emits only a structured review record or safe abstention;
it does not infer identity, mutation, proteins, proteoforms, isoforms,
glioma-specific biology, kinase activity, treatment, consent, or biological
truth.

## Authority and dependency

- Dossier SHA-256:
  `0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`.
- Exact authority slice: `GLIO-PROTEOGEN_240_Module_Dossier.md:6736-6776`.
- Base: `33a4947` (current `main` after the latest merged module lane).
- Parent: `proteotype`; owner Platform engineering; S2/G4; ABI
  `0.1.0-provisional`.
- Upstream remains a caller-declared M19-05 media reference; no external
  content is dereferenced or authenticated.

## Depth delivered

- Declared the M19-06 prohibited-claim vocabulary in the contract and every
  JSON Schema metadata export.
- Added typed `prohibited_claim_boundary` findings.
- Runtime scans discrepancy descriptions, reviewer roles and rationales, and
  all caller-provided configuration/entry/assignment evidence claims before a
  record is emitted.
- Any prohibited claim produces a review-required abstention with no
  adjudication record, preserved request/provenance, and a typed finding.
- Added six-surface adversarial coverage plus API/CLI parity and evaluator
  coverage for the same safe-failure behavior.

## Commit chain

| Stage | Commit |
| --- | --- |
| contract/schema boundary | `2db477a0` |
| runtime/replay boundary | `95df3115` |
| evaluator/fixture closure | `0a9f3a3b` |
| evaluator import hygiene | `b4fdf5fa` |
| strict typing closure | `d35f2156` |

## Gates and receipts

- Focused contract/runtime/interface/evaluator suite: **51 passed**.
- Evaluator: **9/9** declared and executed; **8/8** adversarial; fixture
  authority and claims-ceiling abstention passed.
- Scoped branch-enabled coverage: **97%** (496 statements, 9 missed; 112
  branches, 8 partial), using only the M19-06 contract/runtime source scope.
- Locked 25-call benchmark: mean **1,617,904 ns**, p50 **1,565,000 ns**, p95
  **1,867,400 ns**, within 500,000,000/750,000,000 ns budgets.
- Strict MyPy: clean across **16 files**. Ruff check/format and compileall:
  clean.
- Two pinned wheel/sdist builds were byte-identical; isolated wheel import
  passed with version `0.1.0` and 18 prohibited terms exported.

## Python LOC

Against `33a4947`, this lane changes **7 Python files**, with **386
additions, 5 deletions, +381 net LOC**. Current tracked total is **634,299
Python LOC**.

Package, evaluator, benchmark, and scoped coverage receipts are in
`release-evidence/m19_06_boundary_depth/`.
