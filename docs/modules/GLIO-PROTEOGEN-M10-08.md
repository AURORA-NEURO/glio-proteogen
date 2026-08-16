# GLIO-PROTEOGEN-M10-08 — Evidence and explanation publisher

M10-08 owns the versioned evidence bundle and explanation object beneath the
Pathway/proteotype factors boundary. It records caller-declared attribution,
diagnostics, assumptions, counter-evidence, uncertainty, limitations,
provenance, and reconstruction evidence for the parent target
`protein_rna_discordance`.

The implementation is deliberately provisional because the dossier does not
freeze endpoint names, media types, operation names, or an M10-07 handoff
ABI. The contract advertises `0.1.0-provisional` and carries an explicit
pending-owner-confirmation marker in every exported schema.

## Safety boundary

The publisher never traverses raw external payloads, authenticates caller
claims, infers identity or consent, mutates upstream evidence, converts
unsupported evidence into a negative finding, performs generic all-omics
fusion, infers kinase activity, or recommends treatment. Its `emits_parent`
flag is permanently false; publication is an evidence envelope, not a new
scientific claim.

Seven upstream controls are checked before request validation or evidence
access: approved configuration, identity/lineage, provenance, consent,
quality, support, and intended use. Every result retains all seven decisions,
the consent state, input digests, and explicit limitations.

## Publication semantics

A complete request needs all four source kinds (mass-spectrometry proteome,
genome/transcriptome, PTM annotations, and the upstream protein-RNA result),
at least one assumption, counter-evidence item, reconstruction step, and
evidence reference. A complete envelope is structurally published with
human review required because the ABI and evidence authority remain
provisional. Missing closure abstains with no bundle or explanation and a
review-required support status.

The uncertainty profile explicitly marks measurement, sampling, parameter,
model-form, identification, support, and transport dimensions as
`not_estimable`; no estimator is executed by this provisional publisher.
Canonical request and result digests make repeated execution byte-stable and
make tampering fail closed.

## Interfaces and verification

The isolated FastAPI app exposes provisional schema, validate, publish, and
verify routes. The Typer app exposes matching `export-schema`, `validate`,
`publish`, and `verify` commands. Both use bounded duplicate-safe JSON,
strict JSON-native validation, sanitized diagnostics, and replay verification.

The release evidence records the dossier digest and exact lines, evaluator
matrix, benchmark boundary and budgets, branch-enabled coverage, package
artifacts, and isolated wheel import verification.
