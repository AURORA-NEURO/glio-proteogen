# GLIO-PROTEOGEN-M08-02 — representation and feature constructor

M08-02 owns a versioned analysis representation below Transcript-protein
discordance. It binds mass-spectrometry proteome, genome/transcriptome, PTM
annotations, identity/lineage, provenance, consent, quality, support, intended use,
and approved configuration references without mutating upstream evidence.

The implementation constructs deterministic feature values from content-addressed
inputs and records complete source artifacts, source fields, ordered transformations,
policy evidence, and leakage-safe status for every feature. It refuses construction
when lineage contains outcome/future/target/label/response fields or when source
artifacts are duplicated. Failed checks produce an abstained result with review
required support status, never a negative finding.

The result exposes all seven uncertainty dimensions as explicit non-estimable states
until an owner-approved estimator is frozen. It carries privacy-minimized control
decisions, consent state, identity binding, provenance, evidence, limitations, and a
canonical digest. Replay verification checks both result digest and canonical bytes.

This module does not emit `protein_subtype`, kinase activity, generic all-omics fusion,
identity inference, or treatment recommendations. Its provisional API surface is
available through the strict FastAPI, Typer, and parse-once plugin adapters.

See `docs/evidence/M08-02.md` for gates and the exact dossier authority record.
