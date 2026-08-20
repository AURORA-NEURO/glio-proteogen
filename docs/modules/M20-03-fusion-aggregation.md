# M20-03 fusion and aggregation

Status: provisional implementation; owner review required.

M20-03 is a deterministic, replay-verifiable, component-specific fusion engine beneath
Biomarker-panel translation. It consumes caller-declared M20-02 alignment metadata and
preserves source identity, reliability, uncertainty, evidence, and disagreement state.

Authority: dossier SHA-256 `0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`,
lines `6964-7004`. The implementation is explicitly `0.1.0-provisional`; no frozen ABI,
catalogue, endpoint, or media type is claimed beyond the current behavioral contract.

Safety boundaries:

- No raw artifact traversal, identity inference, consent inference, kinase activity,
  generic all-omics fusion, treatment recommendation, or disagreement erasure.
- Unsupported, not-evaluable, low-reliability, forbidden-scope, or unresolved-disagreement
  inputs abstain safely and preserve review findings.
- Contribution artifacts must be declared by the exact artifact-id/version/digest/media tuple; aggregate
  values are scanned for forbidden biological, kinase, treatment, and diagnosis claims and
  cause abstention rather than being presented as component-specific evidence.
- Seven caller-declared controls are checked before contribution traversal.

The service, plugin, FastAPI adapter, and Typer adapter share the same strict parse-once
request path and replay contract. Verification checks both canonical digests and
regenerates the result from its bound request before comparing the complete canonical
result, so a forged result cannot become valid by recomputing only its own digest. The
evaluator executes eight scenarios and eight adversarial cases; benchmark budgets are
provisional 500 ms mean and 750 ms p95.
