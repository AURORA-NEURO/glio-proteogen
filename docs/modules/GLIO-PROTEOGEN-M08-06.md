# GLIO-PROTEOGEN-M08-06 — Uncertainty Decomposition Engine

## Authority and status

This implementation is derived from the permitted dossier handoff with SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
module slice lines `2776–2819`. The dossier freezes responsibility, safety
controls, seven uncertainty dimensions, sensitivity coverage, and abstention
behavior, but does not freeze endpoint names, media types, estimator catalogue,
or a public ABI. All implementation symbols therefore carry
`0.1.0-provisional`, `provisionalAbi: true`, and
`pendingOwnerConfirmation: true` metadata.

## Responsibility boundary

M08-06 owns uncertainty decomposition beneath the transcript-protein
discordance parent and supports the parent target `protein_subtype`. It emits
only a typed uncertainty object and sensitivity envelope with measurement,
sampling, parameter, model-form, identification, support, and transport
dimensions. It does not emit kinase activity, generic all-omics fusion,
treatment recommendations, a parent subtype/proteotype estimate, raw spectra,
sequences, accessions, or inferred identity/consent.

The request binds the caller-declared M08-05 estimator result, locked policy and
calibration reference, source evidence, execution identity, provenance,
quality, support, intended-use, and consent controls. Source artifact identity
is closed and duplicate artifact IDs are rejected.

## Runtime behavior

The deterministic runtime performs strict preflight before opening upstream
evidence, constructs canonical request/result SHA-256 digests, records seven
control decisions in provenance, and emits a typed non-estimable uncertainty
profile. Without owner-confirmed calibration and synthetic, internal, and
external coverage evidence, it returns `abstained` with `review_required`
support, an explicit finding and abstention reason, and a sensitivity envelope
that carries no invented coverage. Result verification validates digest,
request binding, and exact replay.

HTTP and Typer adapters share the same service seam. Raw JSON is bounded,
duplicate-key rejected, parsed strictly once, and validation diagnostics are
sanitized. Plugin execution requires an issued sealed validation token.

## Verification evidence

- 23 focused tests cover contract invariants, runtime lifecycle, API/CLI/plugin
  parity, evaluator scenarios, and adversarial failure paths.
- The executable evaluator covers safe abstention, all seven uncertainty
  dimensions, deterministic replay, consent denial, tamper rejection, and
  ownership claim ceilings.
- The ten-iteration benchmark uses a frozen fixture and provisional
  2,000,000,000 ns mean / 3,000,000,000 ns p95 budgets.
- Branch-enabled coverage over the M08-06 contract/runtime/interface scope is
  96% (493 statements, 74 branches), above the 95% release threshold.
- Hatchling 1.31.0 built the wheel and source distribution; the wheel was
  installed to an isolated target and imported successfully.

## Known provisional limitations

No calibrated estimator, coverage population, catalogue, or owner sign-off was
supplied by the dossier. The implementation therefore refuses to present a
calibrated interval or biological conclusion. Promotion from the provisional
ABI requires owner confirmation, preregistered nominal-coverage evidence
(85–95% acceptance around the nominal 90% target), synthetic/internal/external
benchmark evidence, reviewer sign-off, and rollback evidence.
