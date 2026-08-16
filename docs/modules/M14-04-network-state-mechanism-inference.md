# GLIO-PROTEOGEN-M14-04 — network, state, or mechanism inference

## Authority and scope

This implementation is bound to dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
lines `4848–4888`. M14-04 is beneath Microenvironment protein deconvolution,
owned by Scientific engineering, safety S2, gate G2, and supports the parent
`protein_subtype`. Endpoint, media type, catalogue identifiers, and model ABI
remain provisional (`0.1.0-provisional`).

## Responsibility and boundary

The module emits only a mechanism posterior or state estimate with assumptions,
alternatives, counter-evidence, typed uncertainty, support, provenance,
evidence, limitations, and explicit abstention. Inputs are opaque references to
proteome, genome/transcriptome, PTM, configuration, identity/lineage,
provenance, consent, quality, support, intended-use, and M14-01 hypothesis
registry objects; no external payload is traversed.

KINOPHOS kinase state, generic all-omics fusion, direct treatment recommendation,
identity/consent inference, upstream evidence mutation, disagreement erasure,
and unsupported-to-negative conversion are prohibited.

## Deterministic method boundary

The reference implementation accepts only caller-declared methods:

- `posterior:<mechanism-id>:<label>:<probability>:<lower>:<upper>` with finite
  values in `[0,1]` and ordered bounds;
- `state:<mechanism-id>:<label>:<active|inactive|present|absent|upregulated|downregulated|stable>`;
- `abstain:<reason>` for explicit safe failure.

Unknown grammar, malformed bounds, unsupported states, missing controls, and
missing counter-evidence produce no estimate, typed unsupported support,
machine-readable finding, human-review requirement, seven non-estimable
uncertainty dimensions, and preserved counter-evidence references.

The selected architecture is a PTM-aware state model; the alternate is
isoform-aware quantification; the fallback is a proteoform probabilistic model.
Quality controls validate identity, version, units, completeness, assay support,
and parent-specific quality, quarantining unresolved inputs. Synthetic truth and
positive controls must be recovered, negative controls rejected, and mature
baselines exceeded.

## Interfaces and release evidence

`M1404MechanismEngine`, `M1404Service`, and `M1404Plugin` provide deterministic
typed execution, parse-once JSON capability, and replay verification.
`glio_proteogen.adapters.m1404` exposes sanitized FastAPI schema/mechanism/
verify routes and Typer export-schema/infer/verify commands with no-overwrite
output behavior.

Release records are bound in:

- `release-evidence/m14_04/evaluation.json`
- `release-evidence/m14_04/benchmark.json`
- `release-evidence/m14_04/coverage.json`
- `release-evidence/m14_04/package.json`
- `docs/evidence/M14-04.md`
- `docs/traceability/M14-04.csv`

The evidence is scoped to M14-04 and is not a claim that the full dossier is
complete.
