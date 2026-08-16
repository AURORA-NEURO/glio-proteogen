# GLIO-PROTEOGEN-M09-03 — mature baseline estimator

M09-03 owns the mature baseline estimator beneath the `complex_activity` parent. The current
implementation is a deterministic, transparent statistical baseline over immutable caller-declared
references. It preserves the dossier's locked-preprocessing, tuning, uncertainty, diagnostics,
safe-abstention, and human-review boundaries while the public ABI and estimator catalogue remain
provisional.

## Authority and ownership

- Authority: `GLIO-PROTEOGEN_240_Module_Dossier.md`, SHA-256
  `0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, lines 3004–3047.
- Owner/safety/gate: Bioinformatics / S2 / G1.
- ABI state: `0.1.0-provisional`; owner confirmation remains required before promotion.
- Parent target: `complex_activity`; `emits_parent` is explicitly false.
- Inputs: the provisional M09-02 representation handoff, mass-spectrometry/genome/transcriptome/
  PTM references, locked preprocessing/tuning/uncertainty/benchmark artifacts, and all seven
  identity, provenance, consent, quality, support, intended-use controls.
- Outputs: one complex-activity baseline estimate, typed uncertainty, diagnostics, evidence,
  provenance, limitations, or a safe abstention requiring human review.

## Boundary and safety behavior

The request and result contracts reject duplicate references, missing locked configuration evidence,
handoff duplication, prohibited ownership claims, duplicate diagnostics, and estimated results with
failed or non-evaluable diagnostics. Canonical request and result digests bind every output to exact
input content. The runtime performs consent, identity, configuration, provenance, quality, support,
and intended-use preflight before any score is computed.

Scores are deterministic SHA-256-derived fixture values. They are not a clinical or biological truth
claim and do not dereference external artifacts. Missing, incomplete, unsupported, not-evaluable,
out-of-domain, calibration-unlocked, discrepancy, and conflict markers abstain. Abstention carries
no estimate, explicit findings, seven non-estimable uncertainty dimensions, and a review-required
support status; no unsupported evidence becomes a negative finding.

The module never emits kinase activity (owned by KINOPHOS), generic all-omics fusion, treatment
recommendation, identity/consent inference, protein-level subtype claims, or an upstream mutation.

## Interfaces and evidence

The isolated FastAPI app exposes strict schema, `validate`, and `estimate` routes. Typer exposes
`export-schema`, `validate`, and `estimate`, rejects existing output paths, and exits nonzero after
writing an abstention result. The plugin uses a parse-once weak validation token; execution requires
the issued token and an unchanged request digest.

Evidence is authority-bound in `tests/fixtures/m09_03/scenarios.json` and the traceability CSV.
`evals/m09_03/run.py` verifies estimated, unsupported, OOD, missing, replay, tamper, determinism,
uncertainty, and ownership-boundary scenarios. `evals/m09_03/benchmark.py` measures ten public
construction calls against provisional 2e9/3e9 ns mean/p95 budgets. Release records remain explicit
that issuer authority, biological validation, calibration, transportability, reviewer sign-off,
and clinical use are outside this software gate.
