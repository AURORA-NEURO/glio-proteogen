# M21-03 internal benchmark and ablation

Status: provisional implementation; Data engineering owner review required.

M21-03 is the metadata-only internal benchmark boundary beneath Reference
material/spike-ins. It consumes a caller-declared M21-02 synthetic-truth result
and explicit benchmark material, then emits a locked-split dossier containing
simple and mature baselines, component ablations, benchmark metrics, and
compute-matched comparisons. It never runs a biological model or emits a
complex-activity estimate.

Authority is the permitted dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
slice `GLIO-PROTEOGEN_240_Module_Dossier.md:7324-7364`. The ABI remains
`0.1.0-provisional`; no frozen endpoint, catalogue, or production media type
is claimed. The immediate dependency is M21-02 at `7c2b50ee`; its
`application/vnd.glio-proteogen.m21-02+json` input is caller-declared and is
not imported, authenticated, traversed, mutated, or relabeled.

Contract and safety boundaries:

- A request must bind execution identity, the exact M21-02 media type, a
  source-artifact set containing that upstream reference, a locked split,
  simple and mature baselines, component ablations, and compute-matched
  comparisons.
- Baseline, metric, ablation, comparison, source, and finding IDs are closed;
  comparison references must resolve to declared runs; ablation deltas and
  compute tolerances are canonical.
- Seven caller-declared controls are checked fail-closed before metadata
  benchmarking. Replay verifies the request digest, deterministic result ID,
  and canonical result digest.
- Unsupported or denied inputs do not become negative findings. Results carry
  explicit support, provenance, seven uncertainty dimensions, evidence, and
  limitations, with `emits_parent=false`.
- KINOPHOS kinase ownership, generic all-omics fusion, treatment
  recommendation, identity/consent inference, upstream mutation, and
  unsupported-to-negative conversion are prohibited.

The strict parse-once plugin, FastAPI adapter, Typer adapter, service, evaluator,
and benchmark share one canonical request/result path.
