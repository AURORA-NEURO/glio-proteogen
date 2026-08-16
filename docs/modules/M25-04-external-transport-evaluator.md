# M25-04 external transport evaluator

Status: provisional implementation; ML engineering owner review required.

M25-04 is the caller-declared external transport boundary beneath
Uncertainty/stability/abstention. It independently validates site, lab,
platform, treatment era, population, disease class, and specimen transport,
then emits only a transportability report and support-domain update. It does
not authenticate upstream issuer authority, traverse raw upstream content, or
emit a proteotype estimate.

Authority is the permitted dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
slice `GLIO-PROTEOGEN_240_Module_Dossier.md:8744-8786`. The ABI remains
`0.1.0-provisional`; no frozen endpoint, catalogue, or production media type
is claimed. M25-02 and M25-03 are caller-declared media boundaries only; no
unpublished upstream service or runtime import is used.

Contract and safety boundaries:

- All seven transport dimensions are required, uniquely identified, and
  independently validated with source/target domains, specimen, assay,
  calibration floors, evidence, and typed uncertainty.
- Supported, narrowed, and not-evaluable states are closed. A narrowed domain
  is visible as limited support; not-evaluable input abstains without a report.
- Seven caller-declared controls are checked fail-closed before transport
  declarations are read. Missing, denied, malformed, or hostile inputs cannot
  become a negative finding or an inferred biological claim.
- Replay verifies canonical request digest, deterministic result identity,
  support-domain report, provenance module, and canonical result payload digest.
- FastAPI and Typer adapters parse once, sanitize errors, refuse output
  overwrite, preserve canonical parity, and expose safe abstention exit codes.
- KINOPHOS kinase-state ownership, generic all-omics fusion, direct treatment
  recommendation, identity/consent inference, disagreement erasure, raw
  content traversal, upstream mutation, and unsupported-to-negative findings
  are prohibited.

Transport evidence is caller-declared and not issuer-authenticated. The result
exposes all seven uncertainty dimensions and requires human review for critical
discrepancy, novel/OOD state, support override, claim promotion, release
exception, or unresolved biological conflict.
