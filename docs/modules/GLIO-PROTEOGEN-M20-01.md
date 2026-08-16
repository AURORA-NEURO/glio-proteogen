# GLIO-PROTEOGEN-M20-01 — upstream contract resolver

## Authority and scope

M20-01 is traceable to dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact lines
`6876-6916`. The ABI is `0.1.0-provisional`; the dossier is behavioral authority only
until the ML engineering owner confirms endpoint, catalogue, and media details.

The module owns typed upstream discovery and compatibility beneath Biomarker-panel
translation. It resolves caller-declared source kind, media type, intended use, version
compatibility, consent, support, provenance, quality, and uncertainty into a validated
upstream bundle or an explicit review-required abstention. It targets `protein subtype`
and never emits the parent result.

It does not own KINOPHOS kinase state, generic all-omics fusion, treatment recommendation,
identity or consent inference, upstream mutation, relabeling, disagreement erasure, or
unsupported-to-negative conversion. Source bytes are never traversed by this resolver.

## Contract closure

The request carries a locked configuration, typed compatibility rules, candidate artifacts,
seven caller-declared controls, evidence, and source references. Candidate identifiers,
artifact digests, evidence digests, and outcome buckets are unique and closed. Every
candidate is classified into selected-compatible, rejected-incompatible, or unresolved-
unknown; an empty selection is valid only for an abstained result.

The result binds the exact canonical request digest and derives its result identifier from
that digest. A validated result has a selected supported bundle; an abstained result has
no bundle, an explicit reason, review-required support, typed findings, and human-review
escalation. Result payload digests and replay verification reject request, identity, or
content tampering.

## Runtime controls and uncertainty

Strict preflight requires approved configuration, resolved identity lineage, accepted
provenance, granted consent, accepted quality, accepted support, and accepted intended
use. Every control is recorded in a seven-entry provenance record. Candidate compatibility
is evaluated deterministically against locked rules, with media/version/provenance/support
failures preserved as typed findings.

The output carries measurement, sampling, parameter, model-form, identification, support,
and transport uncertainty. Contract resolution marks each dimension `not_estimable`; it
does not estimate biological uncertainty or convert missing evidence into a negative.

## Interfaces and evidence

The standalone adapter exposes strict FastAPI schema/resolve/verify routes and Typer
export-schema/resolve/verify commands. JSON is bounded, duplicate-key safe, parsed once
before typed validation, errors are sanitized, and CLI outputs never overwrite existing
files. The plugin descriptor records ML engineering, S2, G0 ownership and prohibited-scope
boundaries.

The frozen evaluator covers compatible validation, mixed review, unknown and incompatible
abstention, media mismatch, identity gating, replay/tamper rejection, deterministic
reconstruction, uncertainty completeness, and package/import evidence. All engineering
evidence is provisional and requires human review before clinical use.
