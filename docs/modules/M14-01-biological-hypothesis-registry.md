# GLIO-PROTEOGEN-M14-01 — biological hypothesis registry

## Authority and status

This implementation is traced to dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
lines `4716–4759`. The responsibility is beneath Microenvironment protein
deconvolution; owner is Clinical science, safety class S2, and gate G0. The
endpoint, media type, and implementation catalogue remain provisional
(`0.1.0-provisional`) pending owner confirmation.

## Responsibility and boundary

M14-01 registers explicit biological hypotheses for the parent `protein_subtype`.
Each hypothesis carries a mechanism class, target IDs, competing explanations,
falsification rules, evidence tiers, prohibited interpretations, and immutable
source-artifact references. The registry emits only versioned hypothesis and
falsification material with typed uncertainty, support, provenance, evidence,
limitations, and explicit abstention.

The module does not own KINOPHOS kinase state, generic all-omics fusion, direct
treatment recommendation, identity or consent inference, upstream evidence
mutation, disagreement erasure, or unsupported-to-negative conversion. Source
artifacts remain opaque references and are never traversed.

The dossier input boundary includes mass-spectrometry proteome,
genome/transcriptome, PTM annotations, approved configuration, identity/lineage,
provenance, consent, quality, support, and intended-use objects. Quality gates
validate identity, version, units, completeness, assay support, and
parent-specific quality; unresolved inputs are quarantined.

## Contract and runtime invariants

Every hypothesis requires at least one competing explanation, falsification
rule, evidence tier, and prohibited interpretation. Hypothesis and nested rule
IDs are unique. The deterministic runtime evaluates only closed caller-declared
tokens (`supported`/`true` and `passed`/`pass`), preserves refuted or unknown
states as findings, and withholds the registry when any required condition is
not safely evaluable. Abstention requires human review acknowledgement.

Request and result digests are canonical and replay-bound. Seven upstream
control decisions are recorded in provenance, and measurement, sampling,
parameter, model-form, identification, support, and transport uncertainty are
explicit. The reference architecture is a curated rule/enrichment/mechanistic
baseline with PCA/ICA; the advanced option is a Bayesian/state-space/
mechanistic/foundation-assisted model with PCA/ICA; the fallback is
orthogonal-method consensus with negative-control gating and PCA/ICA.

## Interfaces and evidence

`M1401HypothesisEngine`, `M1401Service`, and `M1401Plugin` provide deterministic
typed execution, replay, and strict parse-once JSON capability boundaries.
`glio_proteogen.adapters.m1401` provides sanitized FastAPI schema/register/
verify routes and Typer export-schema/register/verify commands. CLI writes refuse
to overwrite existing outputs.

Release evidence records the evaluator matrix, adversarial cases, scoped
coverage, benchmark, package hashes, isolated imports, and traceability:

- `release-evidence/m14_01/evaluation.json`
- `release-evidence/m14_01/benchmark.json`
- `release-evidence/m14_01/package.json`
- `docs/evidence/M14-01.md`
- `docs/traceability/M14-01.csv`

The evidence is scoped to M14-01 and does not claim completion of the full
dossier.
