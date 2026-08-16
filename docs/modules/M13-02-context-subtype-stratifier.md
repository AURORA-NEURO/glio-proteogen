# GLIO-PROTEOGEN-M13-02 context and subtype stratifier

Status: `0.1.0-provisional` / dossier-behavioral-brief-only. The dossier slice is
authoritative at lines 4400–4443 with SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`.

M13-02 consumes caller-declared, typed context observations beneath the
Variant-peptide channel and emits a typed context profile plus a bounded
applicable-mechanism set targeting `proteotype`. It preserves conflicted and
unresolved observations at the input boundary, quarantines unsupported required
dimensions, and never emits the parent output itself.

## Safety and ownership

- Owner: Clinical science; safety class S2; gate G1.
- Identity, consent, approved configuration, provenance, quality, support, and
  intended-use controls must be accepted before computation.
- Artifact references are opaque and are never opened or traversed.
- KINOPHOS owns kinase-state outputs; M13-02 emits none.
- Generic all-omics fusion, treatment recommendation, identity inference,
  consent inference, upstream mutation, relabeling, and disagreement erasure
  are prohibited.

## Deterministic behavior

The runtime evaluates only the declared observation status and policy-required
dimensions. Supported or limited observations produce a profile; missing,
unresolved, or conflicted required dimensions produce an explicit abstention
with no profile and no mechanism set. Caller-declared mechanism candidates are
reported as applicable only when every required dimension has a supported
observation; otherwise they remain `unknown`, never negative.

Every result contains seven uncertainty dimensions, sensitivity notes, a
content-addressed request/result digest, seven control-decision provenance
records, evidence references, limitations, a human-review flag, and the
provisional-ABI finding. Replay verification rejects altered envelopes.

## Interfaces and evidence

- `src/glio_proteogen/adapters/m1302.py`: isolated FastAPI and Typer adapters.
- `evals/m13_02/run.py`: seven-case fixture-bound evaluator.
- `evals/m13_02/benchmark.py`: repeatable latency wrapper with provisional
  2-second mean / 3-second p95 budgets.
- `tests/fixtures/m13_02/scenarios.json`: locked scenario inventory.
- `docs/evidence/M13-02.md`: risk-control and release evidence inventory.
- `docs/traceability/M13-02.csv`: dossier-to-artifact traceability.
- `release-evidence/m13_02/`: machine-readable evaluation, benchmark, coverage,
  and package evidence checked by `tools/verify_m13_02_release.py`.

Release evidence is candidate evidence only. Owner review, external identity
authentication, scientific qualification, clinical validation, and ABI freeze
remain governed follow-up actions.
