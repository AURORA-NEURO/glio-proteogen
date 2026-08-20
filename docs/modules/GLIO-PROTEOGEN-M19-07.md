# GLIO-PROTEOGEN-M19-07 — downstream typed export

M19-07 owns the versioned, immutable, consent-aware and support-aware
downstream typed export beneath Immunopeptidomic evidence. It supports the
parent output `proteotype` and emits only the signed downstream contract
object. The implementation is intentionally caller-declared: it consumes
typed M19-06 references and never traverses raw content or authenticates an
external issuer.

## Authority

- Dossier SHA-256: `0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`
- Exact dossier slice: lines `6780-6820`
- Owner / safety / gate: Scientific engineering / S2 / G3
- Parent: `proteotype`
- ABI: `0.1.0-provisional` pending owner confirmation

## Safety and contract boundary

The contract requires explicit field documentation and ownership, versioned
compatibility, granted consent, supported input, a caller-declared signature,
seven uncertainty dimensions, provenance, evidence and limitations. Every
request is bound to the seven execution controls and to the M19-06 upstream
media type. Field IDs/names, evidence digests, result identity and canonical
payload digests are closed and immutable. Provenance input identity includes
configuration, consent, field and all seven control evidence digests.

The module does not own kinase state, generic all-omics fusion, direct
treatment recommendation, identity inference, consent inference or negative
findings. Unsupported, missing, OOD, prohibited, mismatched or review-gated
material abstains with human review required; it is never converted into a
negative finding.

## Surfaces

- Contract schemas: `src/glio_proteogen/contracts/m19_07/`
- Runtime/replay/service/plugin: `src/glio_proteogen/modules/c19_immunopeptidomic_evidence/m19_07_downstream_typed_export/`
- FastAPI: `create_m1907_app()` (`validate`, `export`, `verify`, schema route)
- Typer: `export-schema`, `validate`, `export`, `verify`
- Evaluator and benchmark: `evals/m19_07/`
- Frozen fixture: `tests/fixtures/m19_07/scenarios.json`
- Release verifier: `tools/verify_m1907_release.py`
