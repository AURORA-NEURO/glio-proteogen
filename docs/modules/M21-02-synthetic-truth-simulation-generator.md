# M21-02 synthetic truth and simulation generator

Status: provisional implementation; Clinical science owner review required.

M21-02 is a deterministic synthetic-truth and simulation boundary beneath
Reference material/spike-ins. It emits only metadata-only synthetic cases and a
reproducibility manifest for validation and benchmarking. The generator covers
normal, edge, missing, shifted, and adversarial fixture kinds; analytic and
semi-synthetic representations remain explicit. It does not emit a biological
measurement, complex-activity estimate, or parent conclusion.

Authority is the permitted dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
slice `GLIO-PROTEOGEN_240_Module_Dossier.md:7229-7272`. The ABI is explicitly
`0.1.0-provisional`; no frozen catalogue, endpoint, or production media type is
claimed beyond the behavioral contract. The upstream M21-01 ABI is published at
`e74a4135`; M21-02 binds only its caller-declared
`application/vnd.glio-proteogen.m21-01+json` artifact and does not import or
traverse an M21-01 service.

Safety and reproducibility boundaries:

- Seven caller-declared controls are checked fail-closed before generation:
  configuration, identity lineage, provenance, consent, quality, support, and
  intended use.
- The generation seed, requested fixture kinds, requested count, case IDs,
  truth labels, perturbation labels, and manifest digest are deterministic and
  replay-verifiable. No raw scientific content is read or synthesized.
- Missing, shifted, and adversarial labels are fixture states, not biological
  negative findings. Unsupported input, denied controls, malformed provenance,
  and media mismatch fail closed.
- All seven uncertainty dimensions, support, provenance, evidence, limitations,
  and non-emission of the parent target are explicit in every result.
- KINOPHOS kinase ownership, generic all-omics fusion, treatment recommendation,
  identity/consent inference, upstream mutation, relabeling, disagreement
  erasure, and unsupported-to-negative conversion are prohibited.

The strict parse-once plugin, FastAPI adapter, Typer adapter, service, evaluator,
and benchmark share one canonical request/result path. Release evidence records
the frozen fixture digests, adversarial closure, package hashes, and generated
artifact cleanup.
