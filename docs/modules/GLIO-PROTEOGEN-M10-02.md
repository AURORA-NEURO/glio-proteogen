# GLIO-PROTEOGEN-M10-02 — representation and feature constructor

M10-02 owns a versioned analysis representation beneath C10 Pathway/proteotype factors. The
installed lane is a deterministic, schema-first constructor with explicit transformation,
scaling, mask, covariate, provenance, and feature-lineage records. It consumes only strict
caller-declared feature values and content-addressed references; it never opens external
artifact bytes.

Authority is the permitted dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, lines 3320–3363. The
public ABI, feature catalogue, media type, and capacities remain provisional (`0.1.0-provisional`)
until owner confirmation. The dossier binds Bioinformatics / S2 / G1, parent target
`protein-RNA discordance`, and the responsibilities below.

## Locked boundaries

- Seven upstream controls are checked before feature traversal: approved configuration,
  identity/lineage, provenance, consent, quality, support, and intended use.
- Every emitted feature has a unique identifier, source artifact, transformation lineage, and
  leakage-safe marker. Fitted transformations require an explicit fit artifact; fit-free
  transformations cannot carry one.
- Missing, masked, unsupported, unknown, or non-evaluable inputs abstain with review required.
  They never become zero, negative evidence, or a constructed representation.
- Replay binds the exact request digest and result payload digest. Tampered results fail replay.
- The module does not emit the parent discordance output and does not infer identity, consent,
  kinase activity, all-omics fusion, or treatment recommendations.

## Runtime architecture

The reference implementation uses a strict Pydantic contract, a deterministic engine, a stateless
service seam, a parse-once plugin capability, isolated FastAPI routes, and Typer commands. The
method catalogue records elastic-net consequence, mature statistical/rule-based, and selective
fallback names, while this lane only applies the bounded operations explicitly present in the
locked configuration. Artifact references are replay boundaries, not dereference permissions.

## Evidence and recovery

The frozen evaluator covers supported construction, complete lineage, unsupported and missing
abstention, unsupported transformation abstention, parent non-emission, and replay. Adversarial
tests cover numeric-string coercion, duplicate transformation outputs, multi-valued observed
features, tampered result digests, strict duplicate-key JSON, and API/CLI parity. The benchmark
measures ten public calls after request construction outside timing; it is a software regression
budget, not evidence of biological accuracy, calibration, transportability, or clinical utility.

Recovery is append-only: a corrected request may supersede a result digest but cannot mutate or
overwrite the prior request, source artifact references, or released result.
