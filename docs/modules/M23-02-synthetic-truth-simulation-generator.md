# M23-02 synthetic truth and simulation generator

Status: provisional implementation; Platform engineering owner review required.

M23-02 is the deterministic synthetic-truth and simulation boundary beneath
Reference material/spike-ins. It emits metadata-only synthetic cases and a
reproducibility manifest for validation and benchmarking. The generator covers
normal, edge, missing, shifted, and adversarial fixture kinds, with analytic
and semi-synthetic representations explicit. It does not emit a biological
measurement, a variant-peptide conclusion, or a parent conclusion.

Authority is the permitted dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
slice `GLIO-PROTEOGEN_240_Module_Dossier.md:8000-8040`. The ABI is explicitly
`0.1.0-provisional`; no frozen catalogue, endpoint, or production media type
is claimed. M23-01 is a caller-declared opaque input boundary only, bound by
`application/vnd.glio-proteogen.m23-01+json`; this implementation imports no
M23-01 service and does not traverse upstream content.

Safety and reproducibility boundaries:

- Seven caller-declared controls are checked fail-closed before generation:
  approved configuration, identity lineage, provenance, consent, quality,
  support, and intended use.
- The generation seed, requested fixture kinds, requested count, case IDs,
  truth labels, perturbation labels, and manifest digest are deterministic and
  replay-verifiable. Values are fixtures, not biological measurements.
- Missing, shifted, and adversarial labels are fixture states, not biological
  negative findings. Denied controls, malformed provenance, unsupported input,
  and media mismatch fail closed.
- All seven uncertainty dimensions, support, provenance, evidence, limitations,
  and non-emission of the variant-peptide parent are explicit in each result.
- Kinase activity, generic all-omics fusion, treatment recommendation,
  identity/consent inference, upstream mutation, raw content traversal,
  disagreement erasure, and unsupported-to-negative conversion are prohibited.

The strict parse-once plugin, FastAPI adapter, Typer adapter, service,
evaluator, benchmark, and release verifier share one canonical request/result
path. Release evidence records the frozen fixture digest, evaluator matrix,
benchmark budgets, branch-enabled coverage, package hashes, isolated import,
and generated-artifact cleanup.
