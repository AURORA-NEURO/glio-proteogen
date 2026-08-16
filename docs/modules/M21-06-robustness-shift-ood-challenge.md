# M21-06 robustness, shift, and OOD challenge

Status: provisional implementation; Computational biology owner review required.

M21-06 is the robustness challenge boundary beneath Reference material. It
consumes caller-declared M21-05 estimator-result media and explicit challenge
material for missing data, low input, corruption, batch/platform/site shift,
artifact, and novel-state scenarios. It emits a typed robustness surface and
OOD evidence only; it never emits a complex-activity estimate or converts an
unsupported challenge into a negative finding.

Authority is the permitted dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
slice `GLIO-PROTEOGEN_240_Module_Dossier.md:7456-7496`. The ABI remains
`0.1.0-provisional`; no frozen endpoint, catalogue, or production media type
is claimed. The M21-05 input is bound by its caller-declared media type only;
this module does not import, authenticate, traverse, mutate, or relabel its
scientific payload.

Contract and safety boundaries:

- A request must bind execution identity, the exact provisional M21-05 media
  type, a source-artifact set containing that upstream reference, all eight
  locked challenge kinds, and a locked configuration.
- Scenario and observation IDs are closed. Every scenario receives exactly
  one observation, and dispositions must agree with the caller-declared
  expected disposition and OOD band.
- Seven caller-declared controls are checked fail-closed before challenge
  evaluation. Replay verifies request digest, deterministic result ID, and
  canonical result digest.
- Unsupported or denied inputs return an explicit safe-failure report with
  support, provenance, seven uncertainty dimensions, evidence, and
  limitations. They never become negative findings.
- Complex-activity estimates, KINOPHOS kinase ownership, generic all-omics
  fusion, treatment recommendation, identity/consent inference, upstream
  mutation, and raw scientific-content traversal are prohibited.

The strict parse-once plugin, FastAPI adapter, Typer adapter, service,
evaluator, and benchmark share one canonical request/result path.
