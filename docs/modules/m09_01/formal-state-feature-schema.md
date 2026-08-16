# M09-01 — formal state and feature schema

## Authority and status

This implementation is traced to GLIO-PROTEOGEN-M09-01, dossier lines
2916–2959, at dossier SHA-256
0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181.
The dossier freezes the responsibility and safety boundary, but does not freeze
the public ABI, feature catalogue, endpoint media type, or operational
capacity. Every exported M09-01 symbol is therefore marked
0.1.0-provisional and requires owner confirmation before production use.

## Responsibility

M09-01 defines formal state beneath Complex stoichiometry: typed features with
units and domains, explicit missingness, executable invariants, constraints,
compatibility rules, and migration rules. It validates caller-declared state
and emits typed uncertainty, support, evidence, provenance, and limitations.
It supports the parent target complex_activity but does not emit a parent
estimate.

The runtime rejects or abstains safely for invalid, missing, unsupported, or
non-evaluable evidence. It does not mutate upstream evidence, infer identity or
consent, erase disagreement, convert missingness into a negative finding, own
kinase activity, fuse generic all-omics, or recommend treatment.

## Runtime contract

- Contract models are immutable, strict, extra-forbidding Pydantic models.
- Numeric values are finite; scalar and interval values are bounded by the
  declared feature domain.
- A request supplies exactly one value for each declared feature, with matching
  unit and representation kind.
- The invariant kernel accepts only all_values_observed and bounded scalar
  comparisons such as feature:complex.activity.scalar >= 0.5; arbitrary
  expression execution is impossible.
- Seven upstream controls are checked before schema traversal.
- Results bind the exact request and result payload through SHA-256 digests and
  canonical JSON bytes. Replay validates both digests and byte determinism.
- FastAPI, Typer, and plugin surfaces all parse strict JSON once and share the
  same validation and execution service.

## Outcome semantics

valid means every observed declared invariant is satisfied and support is
supported. invalid means an observed invariant is violated with limited
support. abstained is used for missing/unsupported values or expressions that
cannot be evaluated; it is never a negative biological conclusion.

## Verification

The release evidence records the focused contract/runtime/interface/evaluator
tests, strict typing and lint gates, scoped branch coverage, evaluator matrix,
deterministic benchmark, wheel/sdist checks, and known external limitations.
