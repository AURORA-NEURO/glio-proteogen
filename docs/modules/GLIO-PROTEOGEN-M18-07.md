# GLIO-PROTEOGEN-M18-07 — downstream typed export

M18-07 is a signed, immutable, support-aware downstream export beneath the Spatial
proteomics projection and biomarker-panel parent. It accepts caller-declared upstream
references and configuration, validates ownership and compatibility, and emits a bounded
typed contract only when all seven controls authorize the operation. The ABI remains
explicitly provisional because the dossier is behavioral authority rather than a frozen
endpoint or media catalogue.

## Authority and safety boundary

| Property | Binding |
| --- | --- |
| Dossier SHA-256 | `0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181` |
| Exact slice | `GLIO-PROTEOGEN_240_Module_Dossier.md:6420-6460` |
| Owner / safety / gate | Platform engineering / S2 / G3 |
| Parent | `biomarker panel` beneath Spatial proteomics projection |
| Operation / version | `export_biomarker_panel_downstream_contract` / `0.1.0-provisional` |
| Declared inputs | MS proteome, genome, transcript, PTM references plus configuration, identity, provenance, consent, quality, support and intended-use controls |
| Typed output | Signed contract object, findings, seven uncertainty dimensions, support, provenance, evidence, limitations, or abstention |

The implementation never dereferences or authenticates upstream content, infers identity or
consent, relabels samples, erases disagreements, converts unsupported material into a negative
finding, or recommends treatment. KINOPHOS/kinase, generic all-omics fusion, direct treatment
recommendation and mutation/relabeling paths are outside the responsibility boundary. A
discrepancy, out-of-domain/support issue, claim promotion, release exception or conflict is
review-required rather than silently normalized.

## Contract, runtime and interfaces

- The contract closes unique IDs, parent binding, ownership, compatibility, support and
  immutable signed-envelope fields. Canonical request and result digests bind replay to the
  exact caller-declared request.
- Runtime preflight requires approved configuration, identity lineage, provenance, consent,
  quality, support and intended use. It fails closed before constructing an export when any
  control is withheld or unresolved.
- Supported requests produce a signed bounded contract with explicit evidence and all seven
  uncertainty dimensions. Limited, unsupported, prohibited or review-required inputs produce
  typed abstention with human-review escalation and no unsupported-negative claim.
- FastAPI exposes schema, export and verify routes. Typer exposes `export-schema`, `export` and
  `verify`. Both use strict parse-once validation, sanitized errors and no-overwrite output.
  The plugin descriptor mirrors the Platform engineering/S2/G3 authority ceiling.

## Evidence and release posture

The frozen eight-scenario evaluator exercises supported export, prohibited boundaries,
unsupported material, limited support, compatibility review, consent denial, replay and strict
JSON boundaries. Replay and tamper verification are explicit. The benchmark is a software
regression tripwire, not scientific validation. Release evidence records the exact fixture,
coverage, evaluator, benchmark, package hashes and isolated import check; generated build and
coverage directories are never part of the source release.
