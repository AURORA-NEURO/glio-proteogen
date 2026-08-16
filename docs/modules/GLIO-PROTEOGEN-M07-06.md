# GLIO-PROTEOGEN-M07-06 — Uncertainty Decomposition Engine

## Authority and status

This implementation is derived from the permitted dossier handoff with SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
module slice lines `2416–2457`. The dossier freezes responsibility and safety
behavior, but does not freeze endpoint names, media types, estimator catalogue,
or a public ABI. All symbols in this implementation therefore carry
`0.1.0-provisional`, `provisionalAbi: true`, and
`pendingOwnerConfirmation: true` metadata.

## Responsibility boundary

M07-06 owns uncertainty decomposition beneath the copy-number dosage/attenuation
parent. It preserves seven independently typed dimensions: measurement,
sampling, parameter, model-form, identification, support, and transport. It
also owns a sensitivity envelope and explicit abstention. The module does not
emit a parent proteotype, kinase activity, treatment recommendation, raw
spectra, sequences, accessions, or inferred identity/consent.

The request binds the complete caller-declared M07-05 result reference, policy
and calibration artifact, source evidence, execution identity, provenance,
quality, support, intended-use, and consent controls. Context request IDs and
source digests are closed under validation; duplicate evidence is rejected.

## Runtime behavior

The deterministic runtime performs strict preflight before opening upstream
evidence, constructs canonical request/result digests, records seven control
decisions in provenance, and emits a typed non-estimable uncertainty profile.
Without owner-confirmed calibration and benchmark coverage, the engine returns
`abstained` with `review_required` support, an `abstention_reason`, a
machine-readable finding, and a sensitivity envelope that carries no invented
coverage. Result verification validates the digest, request binding, and exact
replay.

HTTP and Typer adapters share the same service seam. Raw JSON is bounded,
duplicate-key rejected, parsed strictly once, and validation diagnostics are
sanitized. Plugin execution requires an issued, sealed validation token.

## Verification evidence

- Contract, runtime, interface, evaluator, and adversarial tests are module
  scoped under `tests/`.
- The evaluator covers safe abstention, all seven uncertainty dimensions,
  replay determinism, consent denial, tamper rejection, and ownership ceilings.
- The benchmark uses a frozen fixture, ten iterations, and provisional 2-second
  mean / 3-second p95 budgets.
- Coverage is branch-enabled and measured only over the M07-06 contract/runtime
  scope; the release gate is at least 95%.
- Wheel and source distribution checks are performed after the final evidence
  commit; installed-wheel import is required before publication.

## Known provisional limitations

No calibration artifact, estimator catalogue, benchmark population, or owner
sign-off was supplied by the dossier. The implementation therefore refuses to
present a calibrated interval or a biological conclusion. Promotion from
provisional ABI requires owner confirmation, preregistered nominal-coverage
evidence (85–95% acceptance around the nominal 90% target), external/internal
benchmark evidence, reviewer sign-off, and rollback evidence.
