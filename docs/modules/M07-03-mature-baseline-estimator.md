# GLIO-PROTEOGEN-M07-03 — Mature baseline estimator

## Authority and status

This is a deep provisional implementation derived from the permitted
`GLIO-PROTEOGEN_240_Module_Dossier.md` slice at lines 2284–2327. The authority
SHA-256 is
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`.

The dossier fixes the responsibility, safety boundary, uncertainty dimensions,
review triggers, acceptance bar, and G1 evidence obligations. It does not
freeze the M07-02 handoff symbols, operation name, schema inventory, endpoint,
media type, or estimator ABI. This branch therefore declares
`0.1.0-provisional` and `dossier-behavioral-brief-only`; no symbol is a frozen
public ABI until the owner confirms it.

## Contract boundary

M07-03 accepts caller-declared references to the M07-02 representation, mass
spectrometry proteome, genome/transcriptome, PTM annotations, approved
configuration, identity/lineage, provenance, consent, quality, support, and
intended-use controls. The request binds the configuration to the exact M07-02
artifact, preserves source identity, requires locked preprocessing/tuning
evidence, and rejects duplicate artifacts or ambiguous typed estimates.

The provisional result has a typed baseline estimate collection, diagnostics,
seven uncertainty dimensions (measurement, sampling, parameter, model form,
identification, support, and transport), support status, evidence, provenance,
limitations, and explicit human-review state. The current owner-review state
abstains safely because calibration and published-behavior reproduction are not
yet owner-locked.

## Runtime and replay

The engine checks all seven upstream controls before strict validation. It emits
no kinase activity, generic all-omics fusion, treatment recommendation, parent
proteotype, unsupported-to-negative conversion, identity inference, or consent
inference. Result and request digests are canonical and self-consistent.
`M0703Service.verify` and the plugin verification seam validate the receipt and
replay the exact request by default, rejecting payload, request, evidence, or
control mutations.

## Interfaces and release evidence

`adapters/m0703.py` provides an isolated FastAPI app and Typer app. JSON is
parsed once with duplicate-key/non-finite rejection and then validated through a
strict Pydantic adapter. Errors are sanitized; the stable repository-wide API
is intentionally unchanged while this ABI is provisional.

The evaluator covers safe abstention, transitive replay, tamper rejection,
control fail-closed behavior, M07-02 boundary enforcement, duplicate-key
rejection, typed estimate shape, and plugin parity. Release evidence binds the
fixture manifest, evaluation/benchmark/package receipts, coverage, traceability,
and install smoke to the dossier digest and lines above.
