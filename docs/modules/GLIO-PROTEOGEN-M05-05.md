# GLIO-PROTEOGEN-M05-05 — PTM localization artifact detector

M05-05 is a provisional, deterministic detector for declared PTM-localization
artifact evidence. It consumes the compatible M05-04 quality result and emits
typed artifact posteriors, contamination flags, an exclusion mask, findings,
support, uncertainty, provenance, evidence, limitations, and a disposition.

The implementation is deliberately bounded. It does not infer identity,
consent, treatment response, kinase activity, protein/proteoform/isoform
biology, glioma-specific biology, or all-omics conclusions. It never returns
raw input bytes or unvalidated caller mappings. Missing, unsupported,
quarantined, stale, or tampered upstream evidence fails closed to abstention.

Every request and result is canonicalized once. Nested evidence digests,
ledger bindings, result identifiers, and replay verification are recomputed;
unknown fields, duplicate JSON keys, hostile mapping access, oversize input,
and forged execution tokens are rejected before traversal.

The ABI remains provisional pending the authoritative catalogue freeze. The
release record therefore treats this module as an engineering evidence lane,
not as clinical, biological, or production validation.
