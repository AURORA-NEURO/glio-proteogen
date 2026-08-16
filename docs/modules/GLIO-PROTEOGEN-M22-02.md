# GLIO-PROTEOGEN-M22-02 — Synthetic truth and simulation generator

## Contract identity

- Module: `GLIO-PROTEOGEN-M22-02`
- Operation: `generate_protein_rna_discordance_synthetic_truth`
- ABI: `0.1.0-provisional` (dossier ABI is not frozen)
- Authority: `sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`
- Dossier slice: `GLIO-PROTEOGEN_240_Module_Dossier.md:7640-7680`
- Parent: protein-RNA discordance
- Owner/gate: Data engineering / S3 / G1

## Scope

The module generates deterministic analytic and semi-synthetic reference
fixtures. A locked configuration binds the seed, requested fixture kinds,
case count, source artifacts, corpus case IDs, manifest digest, evidence, and
reproducibility metadata. The implementation includes normal, edge, missing,
shifted, and adversarial fixture kinds, explicit findings, typed support and
seven-dimension uncertainty, canonical request/result digests, replay
verification, and tamper rejection.

The service, FastAPI routes, Typer commands, and strict JSON plugin share the
same parse-once contract and fail-closed seven-control preflight. The M22-01
dependency is represented solely by the caller-declared media type
`application/vnd.glio-proteogen.m22-01+json`; this provisional lane does not
invent or import an unpublished M22-01 service symbol.

## Safety boundaries

Generated fixture material is not authenticated scientific truth. Unsupported
media, missing upstream source closure, denied support, invalid controls,
tampered replay material, and malformed JSON are rejected or abstained safely.
The module does not infer identity, treatment, kinase activity, or generic
all-omics conclusions.

## Evidence

The executable evaluator covers eight cases and the locked ten-iteration
benchmark remains below the 500 ms mean and 750 ms p95 provisional budgets.
The scoped branch-enabled coverage gate is 98% against a 95% threshold.
Machine-readable manifests live under `release-evidence/m22_02/`; run
`python tools/verify_m2202_release.py` to validate the non-package evidence.
