# GLIO-PROTEOGEN-M10-01 — formal state and feature schema

M10-01 owns the versioned formal-state and feature-schema boundary beneath Pathway/proteotype
factors. The implementation represents units, domains, missingness, invariants, compatibility,
and migration metadata without dereferencing external scientific content or making a biological,
kinase, all-omics, treatment, identity, or consent inference.

## Authority and provisional ABI

The implementation is derived from the permitted dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact module slice lines
3276–3319. The dossier freezes responsibility and safety boundaries, but not a public endpoint,
feature catalogue, media type, capacity, or ABI. All exported symbols are therefore explicitly
`0.1.0-provisional`, owner-pending, and must not be treated as a production scientific claim.

## Locked behavior

- Models are immutable, strict, finite, extra-forbidden Pydantic contracts.
- Feature definitions close value kind, units, missingness, domains, categories, invariant refs,
  and migration refs. Duplicate IDs and unknown references reject.
- Invariant expressions use a bounded declarative grammar only: presence/missingness, scalar
  comparisons, and closed intervals. No Python expression, import, network access, or content
  traversal is executed.
- Observed scalar, interval, categorical, and vector values retain their declared shape. Missing,
  not-applicable, unknown, and unsupported states never become zero, negative, or an observed value.
- Hard violations return an invalid formal state; soft conflicts remain visible with limited
  support; missing or unsupported evidence abstains with review-required support.
- Consent, resolved identity/lineage, approved configuration, provenance, quality, support, and
  intended-use decisions are checked before feature or invariant traversal.
- Results carry seven explicit not-estimable uncertainty dimensions, current-layer evidence,
  provenance, limitations, request digest, result digest, and a parent ceiling of
  `protein_rna_discordance` with `emits_parent=false`.
- Replay verifies strict result validation, digest closure, and exact canonical bytes. Tampered,
  oversized, malformed, or non-canonical payloads fail closed.

## Interfaces and evidence

The library/service, strict parse-once plugin, FastAPI app, and Typer CLI share the same typed
request and canonical result. Schema export is metadata-only. The evaluator covers supported,
hard violation, soft conflict, missing abstention, authorization denial, replay, and tamper paths.
The scoped adversarial suite is the release gate; it must be rerun after any contract or runtime
change.

See [M10-01 evidence](../evidence/M10-01.md), [manifest](M10-01.manifest.md), and
[traceability](../traceability/GLIO-PROTEOGEN-M10-01.csv).
