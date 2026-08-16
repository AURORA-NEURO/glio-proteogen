# GLIO-PROTEOGEN-M15-06 — perturbation and sensitivity simulator

M15-06 is a provisional, safety-gated simulator for caller-declared in-silico,
parameter-sweep, alternative-prior, assay-perturbation, and mechanism-stress
scenarios over the Longitudinal recurrence proteotype. Its parent target is
`complex_activity`; it emits a bounded sensitivity surface and never emits a
parent activity estimate.

Authority is the dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
lines 5296–5336. The ABI remains `0.1.0-provisional` pending owner confirmation.
The owner is ML engineering, safety class S2, gate G2.

## Boundaries

- The M15-05 upstream is retained as an opaque artifact and bound by exact media
  type; no upstream payload traversal or mutation occurs.
- Numeric responses are deterministic perturbed-minus-baseline values with an
  explicit software envelope and assumptions. They are not biological calibration,
  causal effects, or treatment recommendations.
- Mechanism-stress scenarios require rationale containing an explicit negative-control
  gate. Missing, malformed, unsupported, or out-of-envelope material abstains.
- Kinase activity, generic all-omics fusion, treatment recommendation, identity
  inference, and consent inference are prohibited outputs.

## Verification

The contract closes finite values, scenario limits, required evidence, response
set equality, upstream media binding, canonical request/result digests, derived
result identifiers, explicit seven-dimension uncertainty, provenance, and review
acknowledgement for abstention. FastAPI, Typer, and the strict parse-once plugin
share one service seam. The release verifier checks the frozen fixture digest,
seven-case evaluator, benchmark budgets, branch coverage, traceability, and
wheel/sdist hashes with an isolated import check.
