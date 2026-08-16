# GLIO-PROTEOGEN-M14-06 — perturbation and sensitivity simulator

## Authority and scope

This implementation is bound to dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
lines `4936–4976`. M14-06 is beneath Microenvironment protein deconvolution,
owned by Bioinformatics, safety S2, gate G2, and supports the parent
`protein_subtype`. Endpoint, media type, catalogue identifiers, and model ABI
remain provisional (`0.1.0-provisional`).

## Responsibility and boundary

The module emits only a sensitivity surface and bounded perturbation response,
with assumptions, typed uncertainty, support, provenance, evidence,
limitations, counter-evidence, and explicit abstention. Inputs are opaque
references to proteome, genome/transcriptome, PTM, configuration,
identity/lineage, provenance, consent, quality, support, and intended-use
objects; no external payload is traversed.

KINOPHOS kinase state, generic all-omics fusion, direct treatment recommendation,
identity/consent inference, upstream evidence mutation, disagreement erasure,
and unsupported-to-negative conversion are prohibited.

## Deterministic support boundary

The reference implementation accepts caller-declared numeric baseline and
perturbed values for in-silico, parameter-sweep, alternative-prior,
assay-perturbation, and mechanism-stress scenarios. It computes a deterministic
sensitivity magnitude with ordered finite bounds. Alternative-prior and assay
artifacts remain attached to the response evidence.

Missing/N/A/non-finite values, unregistered model families, scenario-budget
overruns, unavailable counter-evidence, failed controls, and malformed inputs
produce no surface. They yield a typed review-required support decision,
non-estimable seven-axis uncertainty, diagnostic finding, human-review flag, and
preserved caller references.

The primary architecture metadata is Bayesian graph/state-space/mechanistic or
foundation-assisted with a proteome autoencoder; alternate metadata covers
curated rule/enrichment/mechanistic baselines and masked proteome models; the
fallback is orthogonal consensus with negative-control gating. These metadata
choices do not imply that an unfrozen model is executed.

## Interfaces and release evidence

`M1406SensitivityEngine`, `M1406Service`, and `M1406Plugin` provide deterministic
typed execution, strict parse-once JSON capability, and replay verification.
`glio_proteogen.adapters.m1406` exposes sanitized FastAPI schema/sensitivity/
verify routes and Typer export-schema/infer/verify commands with no-overwrite
output behavior.

Release records are bound in:

- `release-evidence/m14_06/evaluation.json`
- `release-evidence/m14_06/benchmark.json`
- `release-evidence/m14_06/coverage.json`
- `release-evidence/m14_06/package.json`
- `docs/evidence/M14-06.md`
- `docs/traceability/M14-06.csv`

The evidence is scoped to M14-06 and is not a claim that the full dossier is
complete.
