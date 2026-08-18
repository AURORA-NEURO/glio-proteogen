# GLIO-PROTEOGEN-M06-08 — Evidence and explanation publisher

## Authority and status

This implementation is a deep provisional lane derived from the permitted
`GLIO-PROTEOGEN_240_Module_Dossier.md` slice at lines 2144–2184. The authority
SHA-256 is
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`.

The dossier freezes responsibility, safety boundaries, evidence requirements,
and gates but does not freeze an operation name, schema inventory, endpoint,
media type, estimator ABI, or release receipt. The branch therefore declares
`0.1.0-provisional` and `dossier-behavioral-brief-only`; it must not be treated
as a public ABI until the owner confirms those symbols.

## Runtime contract

The provisional operation accepts opaque references to the M06-07 result and
source artifacts plus explicit assumptions, counter-evidence, and ordered
reconstruction steps. It validates all seven caller-declared controls before
strict Pydantic validation. The engine emits a versioned result envelope with:

- content-addressed request and result digests;
- source/evidence references, explicit limitations and seven-dimensional
  non-estimable uncertainty;
- typed support status and an abstention reason when publication gates are not
  owner-locked;
- provenance records for configuration, identity/lineage, provenance, consent,
  quality, support, and intended use;
- an explicit `human_review_required` flag.

No raw spectra, peptide strings, accessions, sequences, kinase state, generic
all-omics fusion, biomarker-panel emission, or treatment recommendation is
accepted or emitted. The engine never infers identity, consent, support, or a
negative finding from missing/unsupported evidence.

## Verification and interfaces

`M0608Service.verify` validates the result digest and replays the exact request;
the plugin exposes the same verification seam. The compatibility `replay`
keyword remains accepted, but cannot downgrade verification to a digest-only
receipt check: a caller that changes a nested explanation, evidence, or
provenance field and recomputes the outer digest is rejected by deterministic
reconstruction. The dedicated provisional FastAPI app uses a parse-once strict
JSON boundary and sanitized validation diagnostics. The Typer app provides
deterministic `export-schema`, `validate`, `publish`, and `verify` commands;
`verify` uses the same mandatory reconstruction path. These adapters are
intentionally isolated from the repository-wide frozen CLI while the ABI
remains provisional.

## Gates

The locked evaluator covers safe abstention, transitive replay, tamper
rejection, unresolved-control fail-closed behavior, explicit M06-07 binding,
duplicate-key rejection, and prohibited parent emission. The benchmark times
only `M0608Service.execute` and uses provisional 2 s mean / 3 s p95 budgets.
Release evidence includes fixtures, evaluator output, benchmark output,
traceability, and package/install smoke results.
