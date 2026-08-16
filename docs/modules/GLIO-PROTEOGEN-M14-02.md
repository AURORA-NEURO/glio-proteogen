# M14-02: context and subtype stratifier

M14-02 owns context and subtype stratification beneath Microenvironment protein deconvolution.
It emits a typed context profile and applicable mechanism set for the `protein_subtype` parent.
The implementation preserves disease class, subtype, age, territory, treatment era, specimen,
platform, and biological context as explicit dimensions rather than hiding them in an opaque
model score.

The ABI is provisional (`0.1.0-provisional`), inferred from the authoritative dossier slice. The
operation, media type, capacities, schema names, and endpoint details are implementation metadata
pending Data engineering owner confirmation.

## Scope and boundary

The request binds a caller-declared Microenvironment deconvolution result, locked stratifier
configuration, required dimensions, context observations, source artifacts, and seven controls:
approved configuration, identity/lineage, provenance, consent, quality, support, and intended
use. Authorization is checked before typed execution or canonical request hashing. Rejected,
unresolved, withheld, or malformed controls fail closed without exposing payload values.

The supported provisional method declarations include Bayesian graph, state-space, mechanistic,
foundation-assisted, curated rule, enrichment, CN-to-protein regression, and orthogonal consensus
with negative-control gating. The runtime is deterministic and stateless; it does not train,
fetch an external model, infer identity or consent, or merge raw omics into an all-omics output.

The safety ceiling prohibits KINOPHOS kinase-state ownership, generic all-omics fusion, direct
treatment recommendation, identity inference, consent inference, upstream relabeling,
disagreement erasure, and conversion of unsupported/missing evidence into a negative finding.
Treatment era is an allowed context dimension; a treatment recommendation is not an allowed
output.

## Contract and runtime behavior

`ContextObservation` preserves supported, limited, conflicted, unresolved, and abstained states.
Supported observations require evidence, unresolved observations cannot carry a normalized value,
and request observation IDs, policy dimensions, profile observation IDs, unresolved dimensions,
mechanism IDs, and result finding IDs are unique. `ApplicableMechanism` requires evidence when
marked applicable.

The result envelope binds the exact canonical request digest, derives its result ID from that
digest, requires evidence-role references, and closes STRATIFIED versus ABSTAINED states. A
stratified result requires a profile, supported support decision, no abstention reason, and no
review flag. An abstained result has no profile or applicable mechanisms, a safe review-required
support state, an explicit reason, and human review required. Unsupported model methods,
conflicted/unresolved observations, incomplete required dimensions, and prohibited proxy tokens
abstain rather than extrapolate.

Seven uncertainty dimensions are explicit: measurement, sampling, parameter, model-form,
identification, support, and transport. Provenance binds input digests, configuration digest,
consent decision, and exactly seven control-decision records. The profile retains all observations
and evidence when stratification succeeds; abstention findings identify conflict, unsupported
proxy, or provisional ABI status.

Canonical replay verifies the result digest and re-runs the exact request. Tampered digests,
changed result state, duplicate JSON keys, forged plugin capabilities, and hostile opaque objects
are rejected.

## Interfaces and evidence

The strict parse-once plugin uses an issued capability token. FastAPI exposes schema, stratify,
and verify routes with content-type checks and sanitized errors. Typer exposes schema export,
no-overwrite stratification, stdout output, and verification. All interfaces share the service
and canonical result representation.

The locked synthetic evaluator contains nine cases: four supported architecture methods,
unsupported method abstention, conflict abstention, prohibited proxy blocking, replay/tamper, and
authorization denial. Final evidence records fixture digest
`sha256:a6222caae33611ae49f087793ee6aa7ec5762867585a2f9ed594ee4999e17ea4`.

The final scoped run executed 29 focused tests and covered 504 statements (500 covered) and 74
branches (72 covered), for 99% branch-enabled coverage against a 95% fail-under threshold. The
benchmark is a provisional engineering tripwire, not a scientific, biological, or clinical
performance claim.
