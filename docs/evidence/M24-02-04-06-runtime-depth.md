# M24-02 / M24-04 / M24-06 runtime depth evidence

This lane implements the provisional runtime surfaces under the biomarker
panel parent target. The dossier handoffs are behavioral briefs only; the
ABI remains `0.1.0-provisional` and owner confirmation is pending. The
runtime therefore consumes typed caller-declared artifacts and never claims
protein, proteoform, isoform, glioma, treatment, kinase, identity or consent
inference.

## Delivered verticals

- **M24-02** generates deterministic normal, edge, missing, shifted and
  adversarial synthetic-truth cases from a locked seed. It binds the M24-01
  media type, manifest reproducibility digest, source evidence, seven-control
  provenance, explicit uncertainty and semantic replay.
- **M24-04** evaluates all seven external transport dimensions (site, lab,
  platform, treatment era, population, disease class and specimen). A failed
  calibration floor abstains without a transport report and preserves the
  narrowing finding.
- **M24-06** challenges all eight robustness surfaces (missing data, low
  input, corruption, batch/platform/site shift, artifact and novel state).
  Unsupported or incomplete challenge material produces a safe-failure report
  and never a negative finding.

All three expose strict parse-once plugins, bounded FastAPI request/verify
routes, Typer schema/validate/execute/verify commands, immutable result
digests, and deterministic replay. The evaluator fixtures cover supported,
abstained, control-denied, self-rehashed/tampered, and replay scenarios.

## Evidence scope

The machine-readable receipts under `release-evidence/m24_02`, `m24_04`, and
`m24_06` are checked by `tools/verify_m24_runtime_release.py`. The benchmark
budgets are provisional 500 ms mean / 750 ms p95. Branch-enabled coverage is
recorded from the focused M24 suite and is intentionally reported rather than
represented as a governed release gate; additional CLI error-path coverage
remains a follow-up hardening item.

Authority records:

- M24-02: dossier slice 8360-8400, Scientific engineering, G1/S3.
- M24-04: dossier slice 8448-8488, Bioinformatics, G3/S3.
- M24-06: dossier slice 8536-8576, Quality engineering, G3/S3.
