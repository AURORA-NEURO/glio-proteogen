# GLIO-PROTEOGEN-M08-05 — mechanism and constraint integrator

M08-05 owns the mechanism and constraint integration boundary below the C08 transcript–protein
discordance workflow. The implementation is deliberately deterministic and content-addressed
while the dossier ABI, ontology catalogue, estimator family, and endpoint media types remain
provisional. It accepts caller-declared mass-spectrometry, genome/transcriptome, PTM, configuration,
identity, provenance, consent, quality, support, and intended-use references and emits only a typed
constraint-aware estimate plus a satisfaction report. It does not emit a parent `protein_subtype`
claim.

## Authority and safety boundary

- Authority: `GLIO-PROTEOGEN_240_Module_Dossier.md`, SHA-256
  `0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, lines 2732–2772.
- Owner/safety/gate: ML engineering / S2 / G2.
- ABI state: `0.1.0-provisional`; symbols, ontology versions, catalogue, and endpoint details
  require owner confirmation before promotion.
- Hard boundaries: no kinase activity (KINOPHOS ownership), generic all-omics fusion, direct
  treatment recommendation, identity or consent inference, upstream mutation, evidence relabeling,
  or unsupported-to-negative conversion.

## Contract and runtime behavior

The request binds the complete provisional M08-04 result by content-addressed artifact reference,
an immutable constraint policy, and seven caller-declared control decisions. Preflight requires
granted consent, resolved identity/lineage, and accepted configuration, provenance, quality,
support, and intended-use controls. Strict Pydantic contracts reject extras, coercion, duplicate
constraint identifiers, malformed estimate shapes, non-finite values, policy/report mismatches, and
digest drift.

The runtime evaluates every policy constraint without fetching external content. `force_violation`
and `unsupported` expressions are deterministic fixture controls, not scientific claims. Hard
violations and unevaluable constraints abstain with no estimates. Soft conflicts remain visible in
the satisfaction report and are not silently allowed to dominate the estimate. Successful estimates
carry interval bounds, support score, applied constraint IDs, evidence references, seven explicit
not-estimable uncertainty dimensions, provenance/control records, and limitations. Results are
canonical JSON and replay verification checks both content bytes and result digest.

## Interfaces and evidence

FastAPI exposes strict schema, validate, and integrate routes. Typer exposes `export-schema`,
`validate`, and `integrate`; existing output paths are rejected and abstention exits nonzero after
writing the canonical result. The plugin uses a parse-once, weakly held validation token so callers
cannot bypass validation or mutate the validated request.

The release evidence includes contract/runtime/interface tests, hard/soft/unsupported/replay
evaluator scenarios, deterministic benchmark output, fixture authority, traceability, and package
import checks. These are software gates only; they do not authenticate external issuers, scientific
measurements, ontology truth, model accuracy, calibration, transportability, or clinical utility.
