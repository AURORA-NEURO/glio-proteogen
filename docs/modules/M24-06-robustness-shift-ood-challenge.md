# M24-06 — robustness shift/OOD challenge (provisional)

## Contract boundary

M24-06 challenges a biomarker-panel workflow across eight declared surfaces:
missing data, low input, corruption, batch shift, platform shift, site shift,
artifact, and novel state. Its upstream input is a caller-declared M24-05
result with media type `application/vnd.glio-proteogen.m24-05+json`. The
source artifact is retained by exact identity; no M24-05 runtime import or
scientific-content traversal is performed.

## Challenge and OOD semantics

Each scenario declares its challenge kind, severity, perturbation,
expected disposition, source artifacts, and evidence. Each generated
observation retains baseline/challenged values, optional envelope bounds,
within-envelope status, OOD score/band, disposition, and evidence. The
configuration locks all eight kinds and an OOD threshold. Duplicate IDs,
missing kinds, unknown scenario references, invalid envelope bounds, and
unsafe dispositions are rejected by the contract.

## Safe failure and controls

The seven control references are checked before challenge material is read.
Supported surfaces produce a result with a robustness surface and supported
status. Review-required or unsupported/OOD scenarios produce no robustness
surface: instead they carry a safe-failure report, explicit abstention reason,
findings, review-required support status, and human-review semantics.

## Interfaces and prohibited outputs

The strict service, parse-once plugin, FastAPI `validate/challenge/verify`
routes, and Typer `export-schema/validate/challenge/verify` commands are
canonical-parity surfaces. Export refuses overwrite, malformed JSON is
sanitized, and replay verifies request digest, derived result ID, and payload
digest. The module never emits a biomarker conclusion, KINOPHOS kinase state,
generic all-omics fusion, treatment recommendation, identity or consent
inference, or raw scientific-content output.
