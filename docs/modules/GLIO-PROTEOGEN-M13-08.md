# M13-08: mechanism evidence dossier beneath the variant-peptide channel

M13-08 assembles a review-ready mechanism evidence dossier beneath the M13-07 variant-peptide
channel. Its output is a typed, deterministic chain of input, mechanism assertion,
counter-evidence, independent validation route, uncertainty, and claim ceiling. The parent
target is `proteotype`; the module does not emit a new parent result or promote a clinical
claim.

The public ABI is explicitly provisional (`0.1.0-provisional`). The dossier slice is authoritative
for scope, while operation names, media types, capacities, and endpoint details remain
implementation metadata pending owner review. The implementation records the authoritative
dossier SHA-256 and line slice in release evidence rather than treating inferred names as frozen
catalogue commitments.

## Responsibility and boundaries

The module accepts an approved configuration, M13-07 upstream result reference, mass-spec /
genome / transcriptome / PTM source references, identity and consent controls, provenance,
quality, support, and intended-use decisions. It retains digests and typed references; it never
traverses or exposes raw identifiers, measurements, clinical labels, or untrusted opaque objects.

Supported provisional model-family declarations are `bayesian_model_averaging`, `state_space`,
`mechanistic`, and `foundation_assisted`. The engine is deterministic and stateless: the selected
family is recorded in the locked configuration, but no training, parameter fitting, or external
model fetch occurs at runtime. Unsupported families produce an abstained result with a
`not_evaluable` diagnostic, an explicit review requirement, and no dossier.

The claim ceiling is part of the reconstructable chain and explicitly blocks:

- KINOPHOS or other kinase ownership;
- generic all-omics fusion beyond the declared evidence links;
- direct treatment recommendations;
- identity or consent inference.

No missing or unsupported evidence becomes a negative biological finding. Authorization is
checked for all seven upstream controls before typed traversal or canonical request hashing:
approved configuration, identity lineage, provenance, consent, quality, support, and intended
use. Any rejected, unresolved, withheld, or otherwise unsafe control fails closed.

## Contract and replay

`MechanismEvidenceDossier` requires unique link, counter-evidence, and validation-route IDs;
known predecessor references; an input link; a claim-ceiling link; a complete validation route;
and evidence references with the `evidence` role. The result envelope binds the exact canonical
request digest, derives its result ID from that digest, requires unique diagnostics and evidence,
and distinguishes READY from ABSTAINED closure. READY requires a supported dossier with no
failed diagnostics or human-review flag. ABSTAINED requires no dossier, a safe support state,
an abstention reason, and human review.

The canonical digest covers the result payload without its digest field. Replay reconstructs the
result from the exact request and compares canonical JSON; digest tampering, altered links,
forged plugin tokens, duplicate JSON keys, and unsafe authorization states are rejected.

Seven typed uncertainty dimensions are always present: measurement, sampling, parameter,
model-form, identification, support, and transport. Provenance retains the module identity,
provisional contract version, request digest, input digests, and seven control-decision records.
Evidence references and limitations remain on both dossier and result envelopes so reviewers can
reconstruct weak links and next validation work without promoting the output beyond its ceiling.

## Interfaces and evaluation

The strict parse-once plugin exposes descriptor, validation, execution, and replay verification.
FastAPI provides schema, dossier, and verify routes with sanitized errors and content-type
checks. Typer provides schema export, no-overwrite assembly, stdout assembly, and verification.
Both adapters use the same service and canonical result bytes; an issued validation token is
required for plugin execution.

The locked seven-case synthetic evaluator covers Bayesian, state-space, mechanistic, and
foundation-assisted ready cases; unsupported-family abstention; visible claim ceiling; replay
and tamper rejection; and authorization denial. The fixture digest is
`sha256:eb929387f8ebe0e28b2fe66e4baa0fde4e2ff35ae7a5b94fa54704551e97303e`.

The scoped release gate executes 37 focused tests with branch coverage enabled. The final run
covered 509 statements (505 covered), 74 branches (72 covered), and 99% total branch-enabled
coverage against a 95% fail-under threshold. The two uncovered branches are defensive replay
exception paths; the evaluator, adapter, contract, and plugin paths are covered.

## Evidence and release

Release evidence is under `release-evidence/m13_08/`; the standard-library verifier checks exact
fixture closure, ten-iteration benchmark budgets, branch-enabled coverage, and hashes/sizes of
the candidate wheel and sdist. Package evidence also records isolated installation/import.
Traceability rows in `docs/traceability/GLIO-PROTEOGEN-M13-08.csv` map each dossier requirement to
an executable contract, runtime, interface, evaluator, adversarial, or release check.

The benchmark is a provisional engineering tripwire, not a scientific or clinical performance
claim. Final release qualification still requires an independent reviewer to confirm dossier
scope, evidence closure, claim ceiling, and rollback/review conditions.
