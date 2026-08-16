# GLIO-PROTEOGEN-M17-04 — intended-use adapter

M17-04 converts caller-declared research output into a bounded intended-use object and policy
decision beneath Metabolomic/lipidomic integration. It validates registered use, audience,
evidence tier, claim ceiling, disclosure sections, support, provenance and uncertainty. The ABI
is explicitly provisional because the dossier provides behavior and architecture options rather
than a frozen field-level interface.

## Authority and boundary

| Property | Binding |
| --- | --- |
| Dossier SHA-256 | `sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181` |
| Exact slice | `GLIO-PROTEOGEN_240_Module_Dossier.md:5928-5968` |
| Owner / safety / gate | ML engineering / S2 / G3 |
| Parent | `variant peptide` context only; `emits_parent=false` |
| Operation / version | `adapt_variant_peptide_intended_use` / `0.1.0-provisional` |
| Upstream boundary | Provisional M17-03 artifact reference only; content is never dereferenced |
| Primary / alternate / fallback | Variant-peptide graph / PTM-aware state model / proteoform probabilistic model (declared; not executed) |
| Output ceiling | Intended-use-specific object, policy decision, typed findings, support, uncertainty, provenance, evidence, limitations, or abstention |

M17-04 never performs KINOPHOS kinase-state work, generic all-omics fusion, treatment
recommendation, identity or consent inference, upstream mutation, disagreement erasure, or
unsupported-to-negative conversion. Treatment, kinase, diagnosis, subtype, and other forbidden
claims are blocked. Clinical/release uses remain review-required even when a bounded object is
adapted.

## Locked implementation and interfaces

- Seven controls are preflighted before registration, claim, display, or upstream traversal.
- Research/internal uses require the corresponding evidence tier; clinical/release uses require
  higher tiers and external review. Display must disclose support, uncertainty, provenance,
  evidence, and limitations.
- Results are deterministic and replay-safe, with canonical request/result digests. Failed policy
  emits no adapted object and returns explicit abstention/review state.
- All seven uncertainty dimensions are `not_estimable`; no calibration or biological truth is
  claimed.

HTTP exposes `GET /v1/contracts/M17-04/{name}/schema` and
`POST /v1/modules/M17-04/intended-use-adaptation`. CLI exposes
`m1704-intended-use export-schema NAME` and `m1704-intended-use adapt REQUEST`. The plugin
descriptor repeats the authority ceiling and provisional ABI.

The evaluator locks seven scenarios and eight adversarial cases; local evidence passes 8/8
(100%, target ≥95%). The benchmark performs one warm-up and 25 public adapter calls. Latency is a
software regression tripwire, not scientific validation.

See the [module manifest](GLIO-PROTEOGEN-M17-04.manifest.md), [evidence inventory](../evidence/M17-04.md),
and [traceability matrix](../traceability/GLIO-PROTEOGEN-M17-04.csv).
