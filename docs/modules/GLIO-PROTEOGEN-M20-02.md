# GLIO-PROTEOGEN-M20-02 — cross-source alignment and reconciliation

## Authority and scope

M20-02 is traceable to dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact lines
`6920-6960`. The ABI is `0.1.0-provisional`: the dossier supplies behavioral authority
only until the Quality engineering owner confirms the endpoint catalogue and media type.
The runtime is stacked on finalized M20-01 commit `a26b0fdf` and accepts only its typed
`application/vnd.glio-proteogen.m20-01+json` artifact boundary.

The module aligns caller-declared protein-subtype source metadata across exactly seven
dimensions: sample, time, territory, analyte, modality, reference, and biological context.
It preserves conflicts in an explicit discrepancy map and returns either a complete aligned
bundle or a review-required abstention. It never reads source bytes or silently promotes
an unresolved comparison.

The output ceiling is an alignment/reconciliation record. M20-02 does not emit the parent
protein subtype, infer identity or consent, mutate upstream evidence, perform KINOPHOS
kinase reasoning, fuse generic all-omics data, recommend treatment, or turn unsupported
inputs into negative findings.

## Contract and replay closure

The locked configuration requires the exact seven dimensions and explicit conflict review.
Observation and discrepancy identifiers, source references, evidence digests, finding IDs,
and result evidence are closed and unique. Critical discrepancies require a resolution;
partial bundles cannot be constructed. The request binds to the provisional M20-01 media
type and source artifact set without assuming a service-level dependency.

Canonical request bytes derive the deterministic result identifier. The result payload digest
excludes only its own digest field, and replay checks request digest, result identity, and
payload digest before returning the immutable result. A supported result has one aligned
observation per dimension, no unresolved discrepancy, a complete bundle, and no review flag.
Any conflict, missing dimension, not-evaluable observation, or unresolved discrepancy emits
an abstention with typed findings, review-required support, seven explicit uncertainty
dimensions, provenance, evidence, and limitations.

## Runtime controls and interfaces

Strict preflight requires accepted approved configuration, resolved identity lineage, accepted
provenance, granted consent, accepted quality, accepted support, and accepted intended use.
All seven caller decisions are recorded in the provenance record. The standalone FastAPI
and Typer adapters parse bounded JSON once, reject unsupported media, sanitize validation
errors, verify replay, and refuse to overwrite CLI output. The sealed plugin descriptor
declares the M20-01 input media boundary, Quality engineering ownership, S2/G1 status,
provisional ABI, and prohibited-scope flags.

## Verification evidence

The frozen evaluator executes aligned, conflicted, and not-evaluable scenarios with replay
checks. Adversarial tests cover incomplete dimensions, unresolved critical discrepancies,
wrong upstream media, duplicate source IDs, JSON round-trip determinism, tamper rejection,
and control preflight. Release evidence records Ruff, strict MyPy, compileall, focused tests,
branch-enabled scoped coverage, bounded benchmark, wheel/sdist hashes, isolated import, and
the standard-library release verifier. This lane remains engineering-provisional and
requires human review before any clinical use.
