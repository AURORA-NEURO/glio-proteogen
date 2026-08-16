# GLIO-PROTEOGEN-M11-01 — biological hypothesis registry

Authority is the project-owner dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, lines
3628–3676.  The dossier freezes the responsibility and safety boundary but
does not freeze a public operation, schema catalogue, or media type.  This
implementation therefore advertises a **provisional ABI** (`0.1.0-provisional`)
and keeps every owner-dependent name explicitly marked as provisional.

## Scope

M11-01 registers caller-declared biological hypotheses beneath the
protein-native subtype component.  A hypothesis carries a mechanism class,
target identifiers, at least one competing explanation, falsification rules,
evidence tiers, and prohibited interpretations.  Source artifacts are opaque
content-addressed references; this module never fetches or parses scientific
content.

The implementation emits only a versioned hypothesis/falsification registry
for the parent `variant_peptide`.  It does not emit kinase activity, generic
all-omics fusion, treatment recommendations, identity/consent inferences, or
upstream relabeling/disagreement erasure.

## Deterministic behavior

- Seven execution controls are authorized before hypothesis traversal.
- The closed evaluator vocabulary recognizes explicit supported/refuted and
  passed/failed declarations; unknown text is `not_evaluable`.
- Every hypothesis and falsification rule receives exactly one evaluation.
- A fully evaluable request produces a supported registry with competing
  explanations preserved verbatim.
- Any refuted, failed, unknown, missing, or unsupported condition produces a
  typed abstention with no registry and required human review.
- Result IDs and request/result digests are canonical and replay-verified.
- Uncertainty is represented on all seven required axes and makes no
  population-calibration claim.

## Provisional interface

The standalone adapter is in `glio_proteogen.adapters.m1101`:

- `GET /v1/m11-01/schema/{name}`
- `POST /v1/modules/M11-01/hypotheses`
- `POST /v1/modules/M11-01/verify`
- Typer group `m1101_app` with `export-schema`, `register`, and `verify`.

These routes are deliberately isolated from the legacy shared adapter until
the Bioinformatics owner confirms the ABI.

## Verification gates

The scoped contract/runtime/adapter suite has 26 tests and 100% statement and
branch coverage (510 statements, 74 branch arcs).  The seven-case evaluator
is fixture-bound and checks supported, abstained, authorization-rejected, and
replay paths.  The ten-iteration benchmark is deterministic and remains well
inside the provisional two-second mean/three-second p95 budgets.
