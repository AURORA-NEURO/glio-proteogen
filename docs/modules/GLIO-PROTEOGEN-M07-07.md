# GLIO-PROTEOGEN-M07-07 — calibration and selective prediction

## Authority and scope

This implementation follows the permitted dossier slice `GLIO-PROTEOGEN-M07-07`,
lines 2460–2503, from dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`.
The dossier freezes the behavioral responsibility and safety controls, but does
not freeze public symbols, endpoint names, media types, calibration artefacts,
metric catalogues, or subgroup ceilings.  The implementation is therefore
`0.1.0-provisional`, carries an explicit provisional ABI marker in every schema,
and is not a clinical or biological performance claim.

## Responsibility and boundary

M07-07 consumes the complete M07-06 uncertainty result, caller-declared
calibration policy and strata, content-addressed source evidence, execution
controls, and explicit candidate declarations.  It emits only a calibrated
estimate, prediction set, support decision, typed uncertainty, provenance,
evidence, limitations, and selective abstention.  It never emits kinase state,
generic all-omics fusion, treatment recommendations, a parent proteotype, raw
spectra, sequences, accessions, or inferred identity/consent.

The candidate envelope is deliberately caller-declared.  An artifact identifier
cannot become a scientific value, and absent or unsupported upstream evidence
cannot become a negative finding.  The runtime selects candidates only after
consent, identity, provenance, quality, support, intended-use, upstream
sensitivity, calibration strata, support, OOD, and calibration-error gates pass.

## Runtime design

- Frozen Pydantic contracts reject unknown fields, non-finite values, duplicate
  candidate/stratum labels, missing numeric prediction labels, duplicate strata,
  and unsupported value/category combinations.
- The provisional policy requires site, platform, disease-class, and subgroup
  strata, each with non-empty samples, observed coverage in 0.85–0.95, and
  calibration error at or below 0.10.  The target is nominal 0.90 coverage.
- Selective candidates require support score, OOD score, calibration error,
  feature identity, a value or category, and stratum bindings.  Locked
  thresholds produce deterministic selected estimates and prediction sets; all
  rejected candidates become bounded diagnostics.
- M07-06 must be supported with an evaluated sensitivity envelope and observed
  coverage in the provisional 0.85–0.95 gate.  Otherwise the result is
  `review_required`/abstained with no estimate or prediction set.
- Request and result digests are canonical.  Candidate, stratum, and source
  artifact ordering is semantic-order normalized for replay.  The sealed plugin
  token records object identity and request digest; forged or mutated tokens are
  rejected.
- FastAPI and Typer both use the repository strict JSON policy, parse-once raw
  JSON validation, sanitized diagnostics, and no-overwrite file behavior.

## Evidence and release gates

The executable eight-case matrix is in `evals/m07_07/run.py` and its pinned
inventory is `evals/m07_07/scenarios.json`.  It covers calibrated selection,
upstream abstention, missing calibration dimension, consent denial, no selected
candidate, replay verification, tamper rejection, and semantic reorder
determinism.  `evals/m07_07/benchmark.py` constructs fixtures outside timing,
warms once, and times ten public service calls against provisional 2 s mean / 3
s p95 budgets.  The package does not traverse external content or execute model
weights.

The release evidence under `release-evidence/m07_07/` records 25 focused tests,
96.36% branch coverage over 729 statements and 150 branches, clean Ruff,
strict MyPy across 15 source files, all eight evaluator cases, and the ten-call
benchmark (2,915,200 ns mean; 3,276,900 ns p95). Hatchling produced a 769,371
byte wheel and 1,441,520 byte sdist, and an isolated wheel import resolved
`M0707Service`. These are engineering gates only and do not promote the
provisional ABI or establish calibration, parity, transportability, or
clinical validity.

Reviewer sign-off, calibration catalogue promotion, subgroup parity ceilings,
and any ABI promotion remain governed external actions.  A corrected result must
supersede the prior digest; no result is overwritten, relabeled, or silently
promoted.
