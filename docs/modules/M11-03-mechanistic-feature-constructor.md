# M11-03 mechanistic feature constructor

Status: `0.1.0-provisional` implementation; the dossier does not freeze the public ABI,
feature catalogue, operation, media type, or capacity limits. This lane therefore keeps
all ABI metadata explicitly provisional.

## Authority and boundary

- Dossier SHA-256: `0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`.
- Exact authority slice: lines 3724–3767, headed **GLIO-PROTEOGEN-M11-03 — mechanistic feature constructor**.
- Owner/safety/gate: Quality engineering / S2 / G1.
- Parent target: `variant_peptide`; output is only a mechanistic feature object with source evidence.
- KINOPHOS owns kinase-state inference. This module does not perform kinase inference,
  generic all-omics fusion, treatment recommendation, identity/consent inference, or
  mutation/relabeling of upstream evidence.

## Contract

The request binds a provisional M11-02 result reference, a locked versioned configuration,
source artifact references, caller-declared feature values, and optional signed topology
relations. Every feature has a kind (pathway, topology, state, lineage, kinetics, spatial,
or regulatory), a closed value representation (scalar, interval, or categorical), a unit,
and complete source/transformation lineage. Relations cannot self-loop, reference unknown
features, or carry weights outside `[-1, 1]`. Configuration transformations and negative
controls are unique. Canonical request/result digests seal replay and tamper detection.

The runtime reads artifact metadata only; opaque artifact payloads are never traversed.
Seven controls (approved configuration, identity/lineage, provenance, consent, quality,
support, and intended use) must be accepted before execution. Missing, unsupported,
out-of-domain, negative-control, unit, topology, and lineage failures produce an explicit
abstention with no feature object and `unsupported` or `review_required` support status.

Seven uncertainty dimensions are always present (measurement, sampling, parameter,
model-form, identification, support, and transport). Because calibration is not frozen by
the dossier, each is explicitly `not_estimable` with a rationale and sensitivity notes.

## Interfaces

- FastAPI: `GET /v1/m11-03/schema/{name}`;
  `POST /v1/modules/M11-03/mechanistic-features` (and the provisional GLIO-prefixed alias);
  `POST /v1/modules/M11-03/verify`.
- Typer: `export-schema`, `construct`, and `verify` in `m1103_app`.
- JSON is bounded, duplicate-key rejected, finite-number checked, parsed once, and returns
  sanitized validation diagnostics. CLI construction never overwrites an existing output.

## Evidence and acceptance

The fixture-bound evaluator covers supported construction, upstream abstention, incomplete
input, unit failure, negative-control failure, replay tamper rejection, and denied control
authorization. It executes 7/7 declared cases. The 10-iteration benchmark records a mean
of 1,129,510 ns, median 1,118,700 ns, p95 1,172,600 ns, and max 1,172,600 ns against
provisional 2,000,000,000 / 3,000,000,000 ns budgets. Scoped branch coverage is 97%
(650 statements, 128 branches) across contracts, runtime, adapter, and evaluator.

The release package is built with hatchling 1.31.0, installed into an isolated target, and
imports the M11-03 contracts and adapter successfully. See `release-evidence/m11_03/` for
machine-readable evaluation, benchmark, and package hashes.
