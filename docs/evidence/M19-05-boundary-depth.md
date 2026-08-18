# M19-05 workflow presentation boundary-depth evidence

This lane hardens the existing M19-05 workflow presentation service against
caller-controlled claim leakage. It preserves the provisional ABI and presents
only a human-review workspace; it does not infer proteins, proteoforms,
isoforms, glioma-specific biology, kinase activity, treatment, identity, or
consent.

## Authority and dependency

- Dossier SHA-256:
  `0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`.
- Exact authority slice: `GLIO-PROTEOGEN-M19-05:6692-6732`.
- Base: `af87f46a` (`M19-03/04` merged main plus current M22 main).
- Upstream binding remains the caller-declared M19-04 aligned evidence bundle;
  no external content is dereferenced.

## Hardening delivered

- Added one contract-level prohibited vocabulary and exposed it in every JSON
  Schema metadata export.
- Added `prohibited_claim_boundary` as a typed finding.
- Runtime scans caller-controlled configuration method/evidence, review titles,
  evidence summaries, uncertainty summaries, evidence claims, and next-action
  labels/rationales before constructing a workspace.
- Any prohibited term produces an abstained result with no workspace, review
  required support status, explicit finding, and preserved request/provenance.
- Added adversarial coverage for all eight text surfaces and API/CLI result
  parity coverage.

## Gates and receipts

- Focused M19-05 contract/runtime/interface suite: **29 passed**.
- Locked evaluator: **7/7** cases passed; fixture SHA-256
  `50bee227561659dcf92d16476338633d610b881d944fbb905f6603288a715bf2`.
- Scoped branch-enabled coverage: **99.28825622775801%** (472 statements,
  2 missed; 90 branches, 2 partial).
- 10-iteration benchmark: mean **2,464,030 ns**, median **2,249,700 ns**, p95
  **2,425,700 ns**, within 2,000,000,000/3,000,000,000 ns budgets.
- Strict package builds were byte-identical. Wheel: **3,688,910 bytes**, SHA-256
  `86ba3f90acd7e6101b733e9541e7c87c0451b0e3b56e07f3f08e0797ab0e5712`.
  Sdist: **4,232,404 bytes**, SHA-256
  `7bd73e40e5fb75d7014faaea6c76987c9dad469d9fee4ec97bb3d6e2ad398d0e`.
  Isolated wheel import passed.

## Python LOC

Against `af87f46a`, this lane changes **6 Python files**, with **169 additions,
6 deletions, +163 net LOC**. Current tracked total: **548,609 Python LOC across
3,718 files**.
