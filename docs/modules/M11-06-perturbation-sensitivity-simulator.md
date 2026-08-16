# GLIO-PROTEOGEN-M11-06 — perturbation and sensitivity simulator

Authority is the project-owner dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, lines
3856–3899.  The dossier freezes the responsibility and safety boundary but
does not freeze a public operation, schema catalogue, media type, or model
family.  This implementation therefore advertises a **provisional ABI**
(`0.1.0-provisional`) and keeps owner-dependent names explicitly provisional.

## Scope

M11-06 simulates caller-declared in-silico perturbations, parameter sweeps,
alternative priors, assay perturbations, and mechanism stress tests beneath
protein-native subtype inference.  It emits a versioned sensitivity surface
with one bounded response per perturbation, typed diagnostics, assumptions,
uncertainty, support, provenance, evidence, and limitations for parent
`variant_peptide`.

The reference implementation is deterministic and content-addressed.  It
uses a locked reference configuration and a negative-control artifact, then
derives a bounded stress-test projection from declared inputs.  It does not
claim causal treatment effects or traverse scientific artifacts.

## Safety and failure behavior

- Seven execution controls are authorized before any perturbation payload is
  examined; missing, withheld, rejected, unresolved, or malformed controls
  are rejected.
- Upstream M11-05 media type, locked configuration, scenario capacity,
  negative-control gating, and explicit assumptions are required.
- Unsupported, missing, novel/OOD, prohibited, or unresolved perturbations
  yield an abstained result with no sensitivity surface and required human
  review.  They never become negative findings.
- Artifact references remain opaque and immutable.  The module never fetches,
  parses, mutates, relabels, or replaces upstream evidence.
- Kinase-state ownership, generic all-omics fusion, direct treatment
  recommendation, identity inference, consent inference, and disagreement
  erasure are outside this module's output boundary.
- Request and result digests are canonical; replay verification reconstructs
  the exact deterministic result and rejects tampering.

## Provisional interface

The standalone adapter is in `glio_proteogen.adapters.m1106`:

- `GET /v1/m11-06/schema/{name}`
- `POST /v1/modules/M11-06/perturbations`
- `POST /v1/modules/M11-06/verify`
- Typer group `m1106_app` with `export-schema`, `simulate`, and `verify`.

Both transports use strict JSON, parse once, sanitize validation errors, and
delegate to the same service seam.  The adapter remains isolated from the
legacy shared adapter until Platform engineering confirms the ABI.

## Verification gates

The scoped contract/runtime/adapter suite has 31 tests and 98.50% weighted
branch-enabled coverage (520 statements, 82 branch arcs).  The nine-case
fixture-bound evaluator checks all perturbation kinds, bounded support,
unsupported/OOD abstention, prohibited ownership, missing negative control,
and denied controls.  The ten-iteration benchmark remains inside the
provisional two-second mean / three-second p95 budgets.  Wheel, sdist, and an
isolated import check are recorded under `release-evidence/m11_06`.
