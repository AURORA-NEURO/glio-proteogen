# GLIO-PROTEOGEN-M24-04 — external transport evaluator (provisional)

## Scope

M24-04 evaluates transportability of caller-declared biomarker-panel
evidence across site, laboratory, platform, treatment era, population,
disease class, and specimen dimensions. It is owned by Bioinformatics,
classified S3, gated at G3, and remains a `0.1.0-provisional` ABI pending
owner confirmation.

## Input and output boundary

The request binds exactly four source artifacts: mass-spectrometry proteome,
genome/transcriptome, PTM annotations, and benchmark package. Every artifact
is retained by `(artifact_id, version, digest, media_type)` and contributes to
the canonical request digest. Each required transport dimension has an
independent validation and evaluation record. The output is a typed transport
report or a safe abstention; `emits_parent` is permanently false and
`parent_target` is the biomarker panel boundary.

## Deterministic safety behavior

Before reading transport metadata, the engine requires accepted configuration,
resolved identity lineage, accepted provenance, granted consent, accepted
quality, accepted support, and accepted intended-use controls. Any missing,
malformed, or denied control fails closed. Supported dimensions produce a
transport report and support-domain update. A `domain_narrowed` or
`not_evaluable` dimension produces an abstained, review-required result with
the reason and finding preserved.

All results expose measurement, sampling, parameter, model-form,
identification, support, and transport uncertainty, plus provenance,
limitations, evidence, and human-review requirements. Canonical replay checks
the request digest, derived result identifier, and payload digest before
re-validating the immutable result.

## Interfaces and evidence

The service, strict parse-once plugin, FastAPI routes, and Typer commands share
the same contract. Validation errors are sanitized; exports do not overwrite;
verification returns a non-success result for tampered or malformed content.
The evaluator fixture covers supported, narrowed, not-evaluable, denied,
replay, tamper, determinism, and parent-boundary scenarios. See
`docs/evidence/M24-04.md`, `docs/traceability/GLIO-PROTEOGEN-M24-04.csv`, and
`release-evidence/m24_04/` for the frozen local release record.

## Prohibited outputs

This module does not authenticate source truth, infer biological or clinical
conclusions, traverse raw scientific content, emit KINOPHOS kinase state,
perform generic all-omics fusion, recommend treatment, or infer identity or
consent. All evidence is explicitly caller-declared and requires human review.
