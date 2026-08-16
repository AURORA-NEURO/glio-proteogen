# M12-01 biological hypothesis registry (provisional)

## Authority and boundary

This implementation follows the authoritative dossier with SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, lines
3996–4039.  The dossier describes a registry beneath the Driver-to-protein
consequence map, with `biomarker_panel` as the parent target.  The public ABI,
operation name, media type, and package placement are not frozen; all are
therefore marked `0.1.0-provisional` and retain pending-owner confirmation.

The module records caller-declared biological hypotheses, mechanism classes,
competing explanations, required evidence, falsification rules, evidence tiers,
prohibited interpretations, typed support, limitations, and provenance.  It
does not emit kinase activity, generic all-omics fusion, treatment
recommendation, identity inference, consent inference, upstream relabeling, or
unsupported-as-negative findings.

## Contract and safety invariants

- Requests are strict frozen Pydantic models with no unknown fields or implicit
  coercion.
- Every hypothesis has unique nested explanation/rule/tier IDs and every
  request has unique hypothesis IDs.
- Results bind the exact canonical request digest and derive their result ID
  from that digest.  Every hypothesis and falsification rule has exactly one
  evaluation.
- Results carry evidence-role references, immutable source artifacts, all seven
  uncertainty dimensions (measurement, sampling, parameter, model-form,
  identification, support, and transport), and seven control decisions.
- A registry is published only when every closed-vocabulary hypothesis is
  supported and every falsification condition passes.  Refuted, unknown,
  failed, missing, or unsupported conditions produce an abstained result with
  no registry, explicit limitations, and human review required.
- Authorization checks approved configuration, identity/lineage, provenance,
  consent, quality, support, and intended use before traversing opaque input
  material.

## Runtime and interfaces

The deterministic runtime lives under the provisional package
`c12_driver_to_protein_consequence/m12_01_biological_hypothesis_registry` and
provides library, service, replay verification, and strict parse-once plugin
seams.  The standalone adapter is
`glio_proteogen.adapters.m1201`:

- `GET /v1/m12-01/schema/{name}`
- `POST /v1/modules/M12-01/hypotheses`
- `POST /v1/modules/M12-01/verify`
- Typer commands `export-schema`, `register`, and `verify`

The adapter uses the strict JSON scanner for duplicate-key and size rejection,
sanitized validation errors, no-overwrite output semantics, and the same
service seam as the library path.

## Evidence and release posture

The evaluator fixture covers supported, multiple-supported, refuted, unknown,
failed falsification, unknown falsification, and denied-control paths.  Release
evidence is stored in `release-evidence/m12_01/` and verified by
`tools/verify_m1201_release.py`.  Package hashes and member counts are generated
only from a clean build output and are checked by the release verifier.
