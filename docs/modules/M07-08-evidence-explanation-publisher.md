# M07-08 — Evidence and explanation publisher

Status: deep-build complete locally; ABI and endpoint are provisional pending owner confirmation.

Authority: `GLIO-PROTEOGEN_240_Module_Dossier.md`, SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, lines 2504–2547.

## Responsibility and boundary

M07-08 owns attribution, diagnostics, assumptions, counter-evidence,
uncertainty, limitations, provenance, and reconstruction for the parent
proteotype workflow. It emits only a versioned evidence bundle and explanation
object. Raw spectra, peptide strings, accessions, sequences, kinase activity,
generic all-omics fusion, treatment recommendations, and a parent proteotype
are outside this module. External evidence is represented by immutable artifact
references and digests; the publisher never traverses or relabels caller-owned
payloads.

## Safety behavior

The seven upstream controls (configuration, identity/lineage, provenance,
consent, quality, support, and intended use) are preflighted before strict
validation. Any unresolved control fails closed. The current provisional
implementation emits a typed abstention with evidence, seven explicit
uncertainty dimensions, limitations, a human-review requirement, and a
provisional-ABI finding. Missing or unsupported evidence is never converted to
a negative biological finding.

Every request is canonicalized to a SHA-256 digest. Results carry a digest of
the result payload with that field removed; verification checks both digests and
replays the exact embedded request by default. The plugin uses a sealed,
single-use validation token so callers cannot execute a forged or mutated
request object. FastAPI and Typer share the same strict duplicate-key and
non-finite-number JSON parser.

## Verification gates

- Contract tests cover strict fields, source role closure, unique identifiers,
  ordered reconstruction, upstream media binding, result-id derivation, and
  abstention/review invariants.
- Runtime tests cover control fail-closed behavior, canonical replay,
  tampering, token forgery, opaque attribution, and prohibited parent output.
- Evaluator fixtures cover eight dossier-derived scenarios; the executable
  evaluator has seven checks because source opacity is asserted as part of the
  evidence-closure check.
- Benchmark timing is limited to `M0708Service.execute` and uses provisional
  2-second mean / 3-second p95 budgets until a frozen performance contract is
  supplied.

No production ABI is claimed by this document. The operation, endpoint, schema
inventory, media type, and upstream M07-07 handoff remain reviewable metadata.
