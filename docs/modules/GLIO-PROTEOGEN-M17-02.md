# GLIO-PROTEOGEN-M17-02 — cross-source alignment and reconciliation

Status: provisional implementation, release evidence complete, ABI not frozen.

## Authority and ownership

- Dossier: `GLIO-PROTEOGEN_240_Module_Dossier.md`
- Authority SHA-256: `0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`
- Exact authority slice: lines `5840-5880`
- Parent component: C17, Metabolomic/lipidomic integration
- Owner: Computational biology / S2 / G1
- Parent target: `variant_peptide`
- ABI: `0.1.0-provisional`; endpoint and media catalogues remain unfrozen

M17-02 aligns caller-declared evidence across sample, time, territory, analyte, modality,
reference, and biological context. It emits an aligned evidence bundle and discrepancy map;
it does not mutate upstream evidence, relabel another module's output, erase disagreement,
infer identity or consent, or convert unsupported/missing evidence into a negative finding.
Kinase activity remains owned by KINOPHOS, and this module does not perform generic all-omics
fusion or direct treatment recommendation.

## Contract boundary

The request binds an execution context, at least two typed source observations, a locked
alignment policy, and source artifacts. The policy must declare all seven alignment axes,
preserve conflicts, quarantine unresolved inputs, and carry a locked configuration with model
reference evidence. Each observation declares modality, sample, time, territory, analyte,
reference, biological context, source artifact, alignment status, and evidence.

The output is one of two explicit states:

- `reconciled`: all seven axes agree, every observation is aligned, the immutable bundle is
  present, support is `supported`, and human review is false;
- `abstained`: no aligned bundle is promoted, discrepancies or boundary markers are retained,
  support is `review_required` or `unsupported`, and human review is true.

The contract closes identity, evidence, disagreement, status, and digest invariants:

- policy axes are unique and cover the complete seven-axis set;
- aligned observations require evidence;
- discrepancy codes match their axis, require review, and name at least two observations;
- discrepancy IDs and observation IDs are unique and membership is explicit;
- aligned bundles cannot hide discrepancies; conflicted/unresolved bundles require a map;
- result IDs derive from the canonical request digest;
- output evidence is non-empty and uses the evidence role;
- finding and discrepancy codes are unique; and
- status, bundle, support, review, and canonical result digest are mutually closed.

## Controls, uncertainty, and provenance

Preflight requires seven caller-declared control decisions:

| Control | Required state |
| --- | --- |
| approved configuration | `accepted` |
| identity lineage | `resolved` |
| provenance | `accepted` |
| consent | `granted` |
| quality | `accepted` |
| support | `accepted` |
| intended use | `accepted` |

The result explicitly carries measurement, sampling, parameter, model-form, identification,
support, and transport uncertainty. Supported alignment uses a caller-declared 0.9 probability;
abstention uses `not_estimable`. Provenance binds the canonical request digest, source artifact
digests, locked configuration, consent decision, actor, timestamp, and all seven control records.

## Alignment and safe failure

The deterministic runtime compares every declared axis across observations. A mismatch produces
an axis-specific discrepancy (`sample_mismatch`, `time_mismatch`, `territory_mismatch`,
`analyte_mismatch`, `modality_mismatch`, `reference_mismatch`, or
`biological_context_conflict`). Non-aligned observations produce `unresolved_alignment`.
Conflict and unresolved states remain reviewable rather than being silently dropped.

Unsupported, unknown, missing, not-evaluable, OOD, abstain, kinase, treatment, all-omics,
identity/consent inference, mutation, relabel, or erasure markers fail closed. The runtime never
turns those markers into a negative biological claim. Replay recomputes the typed request and
rejects digest tampering or non-deterministic reconstruction.

## Dependency boundary

The actual M17-01 exported ABI was inspected at commit `8988a79`: its typed exports are
`VariantPeptideUpstreamResolutionResult`, `ValidatedUpstreamBundle`, and associated resolver
models. M17-02 does not invent an M17-01 service or silently assume a resolver endpoint. Its
request remains self-contained and source-typed; a future frozen integration may bind the
verified M17-01 result explicitly through an ABI decision.

## Interfaces and verification

- FastAPI: `GET /v1/m17-02/schema/{name}`, `POST /v1/modules/M17-02/align`,
  `POST /v1/modules/M17-02/verify`.
- Typer: `export-schema`, `align`, and `verify`; output paths are never overwritten.
- Plugin: strict parse-once validation produces a sealed `ValidatedM1702Request` token.
- Evaluator: ten frozen scenarios cover reconciled alignment, axis conflict, unsupported and
  prohibited abstention, review status, authorization, deterministic reconstruction, replay,
  tamper rejection, uncertainty/provenance completeness, and all-axis alignment.
- Release verifier: `tools/verify_m1702_release.py` validates exact fixture closure, timing
  budgets, branch-enabled coverage, package hashes, and isolated import evidence.

## Human review and explicit non-goals

Human review is required for critical discrepancy, novel/OOD state, support override, claim
promotion, release exception, or unresolved biological conflict. The provisional module is not
a clinical recommendation engine and is not authorized to infer identity, consent, kinase state,
treatment, mutation, generic all-omics conclusions, or unsupported negative findings.
