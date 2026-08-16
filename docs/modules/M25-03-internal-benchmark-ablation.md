# M25-03 internal benchmark and ablation

## Authority and boundary

M25-03 is a provisional Bioinformatics/S3/G2 module beneath the `proteotype`
parent. Its behavioral handoff is limited to dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
slice `GLIO-PROTEOGEN_240_Module_Dossier.md:8764-8804`. The upstream input is
the caller-declared M25-02 synthetic-truth result media type; no M25-02 Python
runtime import or payload traversal is assumed.

## Contract and runtime

- strict contracts close locked nested validation splits, simple and mature
  baselines, component ablations, compute-matched comparisons, metrics,
  findings, provenance, evidence, seven uncertainty dimensions, and explicit
  supported/abstained states;
- request identity, upstream media, source-artifact inclusion, cross-reference
  IDs, score deltas, compute tolerances, and canonical request/result IDs are
  revalidated at the immutable boundary;
- deterministic execution compares only caller-declared metadata and emits no
  proteotype estimate, biological truth, kinase state, treatment advice, or
  generic all-omics fusion;
- seven-control preflight runs before benchmark material is read; denied,
  non-passing, unsupported, malformed, or tampered inputs fail closed;
- FastAPI, Typer, and strict parse-once plugin paths share the same service and
  replay verifier.

## Evidence

The evaluator covers completed benchmarking, baseline/ablation/compute-match
abstention, denial, deterministic reexecution, replay, plugin parity, and the
locked fixture identity. The release evidence directory records exact local
coverage, benchmark, package, and verifier results. ABI and owner confirmation
remain provisional pending dossier governance.
