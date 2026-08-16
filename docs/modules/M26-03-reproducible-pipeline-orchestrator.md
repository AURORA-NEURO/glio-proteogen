# M26-03 — Reproducible pipeline orchestrator

M26-03 is a provisional ML-engineering/G1/S3 orchestration boundary beneath
the `protein subtype` parent. Its responsibility is deterministic execution
of a caller-declared locked workflow: DAG closure, container and environment
capture, retries, checkpoints, execution records, replay manifests, and
immutable result digests.

Authority is limited to dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
slice `GLIO-PROTEOGEN_240_Module_Dossier.md:9124-9164`. The endpoint and
media ABI remain `0.1.0-provisional` pending owner confirmation.

The implementation consumes M26-01 and M26-02 only through their declared
media types (`application/vnd.glio-proteogen.m26-01+json` and
`application/vnd.glio-proteogen.m26-02+json`). M26-02 has no published runtime
ABI in this lane, so the package intentionally does not import or infer one.

Execution is fail-closed on all seven controls: approved configuration,
identity/lineage, provenance, consent, quality, support, and intended use.
The result carries execution attempts, checkpoint digests, environment and
source evidence, seven non-estimable uncertainty dimensions, limitations,
human-review requirement, and `emits_parent=false`. It makes no biological,
identity, consent, kinase, all-omics, treatment, or unsupported-negative claim.

The strict service, FastAPI, Typer, and parse-once plugin adapters share the
same canonical request/result validators. Release evidence is independently
checked by `tools/verify_m2603_release.py`.
