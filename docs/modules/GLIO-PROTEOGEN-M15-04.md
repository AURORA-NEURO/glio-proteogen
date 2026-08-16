# M15-04: network, state, or mechanism inference

M15-04 is the provisional mechanism-inference component beneath the longitudinal
recurrence proteotype. It consumes the bound M15-01 hypothesis result together
with caller-declared proteome, transcript/protein-discordance, PTM, and seven
upstream control references. It emits a posterior or state estimate for the
`complex_activity` parent while retaining counter-evidence, alternatives,
assumptions, typed uncertainty, support, provenance, and safe abstention.

## Authority and boundary

The implementation is grounded in `GLIO-PROTEOGEN_240_Module_Dossier.md`,
SHA-256 `0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`,
exact lines 5208–5248. The owner is Computational biology under S2/G2. The
primary architecture is represented as deterministic provisional metadata for
Bayesian/state-space/mechanistic/foundation-assisted and structure-aware
proteoform inference; curated/enrichment/mechanistic and orthogonal-consensus
alternates remain explicit. KINOPHOS kinase ownership, generic all-omics fusion,
treatment recommendation, identity or consent inference, mutation/relabeling/
erasure, and unsupported-to-negative conversion are prohibited.

## Contract and runtime

The request is locked to the provisional M15-01 result media type and includes
method, model, calibration, source artifacts, and seven control decisions. The
runtime checks controls before strict parsing or hashing, rejects malformed or
hostile opaque inputs, and deterministically emits either a posterior with
ordered probability bounds or a state estimate with no posterior fields.
Supported estimates always include assumptions, alternatives, counter-evidence,
evidence, and a provisional-ABI finding. Unsupported, prohibited, negative
control, OOD, unknown, or uncalibrated declarations produce no estimate, require
review, and remain explicitly abstained.

Request and result digests bind canonical content; result IDs derive from the
request digest. Replay re-executes the request and rejects result tampering or
non-equivalent reconstruction. Provenance records all seven controls, input
digests, configuration, consent, actor, and generation time. All seven
uncertainty dimensions (measurement, sampling, parameter, model form,
identification, support, transport) remain visible with sensitivity notes.

## Interfaces and evidence

The strict plugin uses an issued validate-then-run capability token. FastAPI and
Typer share the typed service and canonical JSON representation, enforce strict
content types and duplicate-key rejection, sanitize errors, and prevent CLI
output overwrite. The evaluator contains nine locked cases covering posterior
and state positive controls, unsupported/negative/prohibited abstention,
replay/tamper, authorization, deterministic reconstruction, and complete
counter-evidence/uncertainty/provenance.

The final scoped gate passed 26 focused tests, Ruff, strict MyPy across 13
M15-04 source/eval/tool files, compileall, and 95.55% branch-enabled coverage
(463 statements, 448 covered; 76 branches, 67 covered; fail-under 95). Ten
benchmark iterations measured 1,412,290 ns mean, 1,249,900 ns median, and
1,319,300 ns p95 against provisional 2e9/3e9 ns budgets. Release evidence,
traceability, package hashes, and tamper-checking verifier are under
`release-evidence/m15_04/`.
