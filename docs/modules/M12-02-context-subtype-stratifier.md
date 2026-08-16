# M12-02 context and subtype stratifier (provisional)

## Authority and boundary

This implementation follows the authoritative dossier with SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, lines
4040–4083.  It is owned by Quality engineering at S2/G1 beneath the
Driver-to-protein consequence map and targets `biomarker_panel`.  The public
ABI, operation name, media type, and package placement are not frozen; all are
therefore explicitly `0.1.0-provisional` pending owner confirmation.

The module emits a typed context profile and applicable mechanism set for
disease class, subtype, age, territory, treatment era, specimen, platform, and
biological context.  It preserves transcript/protein and genomic context as
caller-declared evidence without traversing opaque artifacts.  Kinase state is
owned by KINOPHOS; this module does not emit kinase activity, generic all-omics
fusion, direct treatment recommendation, identity or consent inference, parent
output relabeling, or unsupported-as-negative findings.

## Contract and safety invariants

- Requests are strict frozen Pydantic models with no unknown fields or implicit
  coercion.  Locked configuration, all eight dimensions, immutable upstream
  references, and caller-declared evidence are explicit.
- Results bind the exact canonical request digest and derive their result ID
  from it.  Supported profiles preserve every request observation and every
  result evidence reference uses the `evidence` role.
- A profile is published only when all eight policy dimensions are present
  exactly once and each observation is supported.  Missing, limited,
  conflicted, unresolved, or incomplete-policy cases abstain with no profile
  or mechanism set and require human review.
- All seven uncertainty dimensions (measurement, sampling, parameter,
  model-form, identification, support, and transport) are explicit.  Control
  provenance records approved configuration, identity/lineage, provenance,
  consent, quality, support, and intended-use decisions.
- Opaque artifacts are references only.  Upstream controls are authorized
  before observation traversal; disagreements remain visible and never become
  negative biological findings.

## Runtime and interfaces

The deterministic runtime lives under the provisional package
`c12_driver_to_protein_consequence/m12_02_context_subtype_stratifier` and
provides library, service, replay verification, and strict parse-once plugin
seams.  The standalone adapter is `glio_proteogen.adapters.m1202`:

- `GET /v1/m12-02/schema/{name}`
- `POST /v1/modules/M12-02/context`
- `POST /v1/modules/M12-02/verify`
- Typer commands `export-schema`, `stratify`, and `verify`

The adapter uses duplicate-key and size rejection, sanitized validation errors,
no-overwrite output semantics, and the same service seam as the library path.

## Evidence and release posture

The evaluator fixture covers a supported profile, missing and limited
dimensions, conflicting observations, incomplete policy, and denied controls.
Release evidence is stored in `release-evidence/m12_02/` and verified by
`tools/verify_m1202_release.py`.  Package hashes and member counts are generated
from a clean build output and checked by the release verifier.
