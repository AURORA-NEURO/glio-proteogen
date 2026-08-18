# GLIO-PROTEOGEN-M19-02 — Cross-source alignment and reconciliation

## Authority and scope

M19-02 is traceable to dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact lines
`6560-6600`. The ABI is `0.1.0-provisional`; the dossier is behavioral authority only
until the ML engineering owner confirms endpoint, catalogue, and media details.

The module owns sample, time, territory, analyte, modality, reference, and biological-
context alignment beneath Immunopeptidomic evidence. It emits an aligned evidence bundle
and discrepancy map for the parent target `proteotype`, preserving genomic context,
transcript-protein discordance, treatment history, source identity, and support state.

It does not own KINOPHOS kinase state, generic all-omics fusion, treatment recommendation,
identity or consent inference, upstream mutation, upstream evidence mutation, disagreement
erasure, or unsupported-to-negative conversion. Source bytes are never traversed.

## Contract closure

The request carries a locked seven-dimension configuration, source artifacts, caller-
declared observations, explicit discrepancy entries, seven controls, and immutable
evidence. Source identifiers, content digests, observation identifiers, discrepancy
identifiers, and evidence references are unique and closed. Every non-aligned observation
must have a matching discrepancy entry; aligned observations cannot carry a discrepancy.

The result binds the exact canonical request digest and derives its result identifier from
that digest. An aligned result requires a supported bundle with no review-required
discrepancy. An abstained result carries no bundle, an explicit reason, typed findings,
safe support status, and human-review escalation for critical findings. Result payload
digests and replay verification reject request, provenance, bundle, or content tampering.

## Runtime controls and uncertainty

Strict preflight requires approved configuration, resolved identity lineage, accepted
provenance, granted consent, accepted quality, accepted support, and accepted intended
use. Every control is recorded in a seven-entry provenance record. Caller-declared source
values are compared deterministically; conflicts and non-evaluable dimensions abstain
without being relabeled as negative biology.

The output carries measurement, sampling, parameter, model-form, identification, support,
and transport uncertainty. Alignment marks each dimension `not_estimable`; it does not
estimate biological uncertainty or infer missing identity, consent, or treatment state.

## Interfaces and evidence

The standalone adapter exposes strict FastAPI schema/align/verify routes and Typer
export-schema/align/verify commands. JSON is bounded, duplicate-key safe, parsed once
before typed validation, errors are sanitized, and CLI outputs never overwrite existing
files. The plugin descriptor records ML engineering, S2, G1 ownership and prohibited
scope boundaries.

The frozen evaluator covers supported alignment, ordinary and critical conflicts,
non-evaluable input, authorization gating, replay/tamper rejection, deterministic
reconstruction, uncertainty completeness, and strict plugin parity. All engineering
evidence is provisional and requires human review before clinical use.
