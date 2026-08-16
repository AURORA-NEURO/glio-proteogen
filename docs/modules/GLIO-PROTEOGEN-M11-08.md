# GLIO-PROTEOGEN-M11-08 — mechanism evidence dossier

Status: **provisional implementation; owner review required**  
Authority: `GLIO-PROTEOGEN_240_Module_Dossier.md`, SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, lines
3944–3987.  
Owner / safety / gate: Computational biology / S2 / G3.  
Parent target: `variant_peptide`.  
Provisional contract: `0.1.0-provisional`.

## Responsibility and boundary

M11-08 assembles a review-ready mechanism evidence dossier beneath the
protein-native subtype pathway. It preserves a reconstructable chain from
mass-spectrometry proteome, genome/transcriptome, PTM annotations and the
upstream variant-peptide result through mechanism association, counter-evidence,
validation route, uncertainty and claim ceiling.

The implementation does not dereference caller artifacts, mutate upstream
evidence, infer identity or consent, erase transcript/protein disagreement,
turn unsupported evidence into a negative finding, own KINOPHOS kinase state,
perform generic all-omics fusion, or recommend treatment. Every public symbol,
operation, schema name, media type and endpoint is explicitly provisional until
the owner freezes the ABI.

## Contract surface

The strict Pydantic contract requires:

- immutable source attribution for five source classes;
- locked configuration and source manifest;
- ordered links with explicit predecessors and evidence;
- non-empty assumptions, counter-evidence and validation route closure for a
  ready dossier;
- reconstruction steps with input/output digests;
- explicit seven-dimension uncertainty (`measurement`, `sampling`, `parameter`,
  `model_form`, `identification`, `support`, `transport`);
- a claim ceiling listing prohibited interpretations;
- module-local provenance projected from all seven caller controls; and
- a result digest binding the exact request and result payload.

Incomplete requests remain representable so the runtime can return an explicit
abstention. A ready result contains a dossier and supported status; an abstained
result contains no dossier, carries review-required status, and always requires
human review.

## Runtime and interfaces

`M1108MechanismEvidenceDossierEngine` is deterministic and stateless. It
preflights approved configuration, identity lineage, provenance, consent,
quality, support and intended-use states before reading evidence fields. It
requires all source classes, a mechanism and claim-ceiling link, counter-
evidence, a non-failed validation route and ordered reconstruction. Any missing,
failed or unsupported condition produces safe abstention.

`M1108MechanismEvidenceDossierPlugin` is parse-once: strict duplicate-key JSON
is decoded once, authorized once and converted into an opaque execution token.
`M1108MechanismEvidenceDossierService` exposes validate, execute and replay
verification seams.

The isolated adapters in `src/glio_proteogen/adapters/m1108.py` provide:

- FastAPI schema, validate, assemble and verify routes under `/v1/m11-08`;
- compatibility module routes under `/v1/modules/M11-08`; and
- Typer `export-schema`, `validate`, `assemble` and `verify` commands.

HTTP and CLI errors are sanitized. Tampered result digests fail replay
verification and never become a successful response.

## Review and safety controls

All artifact content is opaque. The dossier records source identity, digest,
media type and caller claim, but never loads raw spectra, genomic rows or
external payloads. The claim ceiling is explicit and includes KINOPHOS kinase
ownership, generic all-omics fusion and direct treatment recommendation as
prohibited interpretations. Critical discrepancies, novel or out-of-domain
states, support overrides, claim promotion and release exceptions remain
human-review gates outside this provisional assembler.

## Evidence commands

```text
uv run pytest -o addopts='' tests/contract/test_m11_08_contract.py \
  tests/contract/test_m11_08_runtime.py \
  tests/contract/test_m11_08_interface.py \
  tests/contract/test_m11_08_evaluator.py \
  tests/contract/test_m11_08_adversarial.py -q
uv run python -m evals.m11_08.run
uv run python -m evals.m11_08.benchmark
uv run python tools/verify_m1108_release.py
```

The release evidence records the exact fixture digest, evaluator matrix,
benchmark samples, scoped branch coverage, package hashes and isolated import
check. These are synthetic structural gates; they do not establish biological
truth, assay performance, clinical utility, external signer authenticity or
owner approval.
