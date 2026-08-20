# GLIO-PROTEOGEN-M27-03

## Reproducible complex-activity pipeline orchestrator (provisional)

| Property | Locked local implementation value |
| --- | --- |
| Authority | Dossier SHA `0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, lines 9484-9524 |
| Module | `GLIO-PROTEOGEN-M27-03` |
| Owner / safety / gate | Quality engineering / S3 / G1 |
| Parent target | `complex activity` context only; no complex-activity estimate or score |
| Operation | `orchestrate_complex_activity_pipeline` |
| ABI | `0.1.0-provisional`; owner confirmation remains pending |
| Upstream | Caller-declared M27-02 artifact reference with media `application/vnd.glio-proteogen.m27-02+json`; no M27-02 service is called |
| Runtime | Deterministic DAG scheduling over caller-declared nodes, container digests, retry policy, checkpoints, environment digest, and reproducible package |
| Safe failure | Unsupported controls, malformed execution, graph errors, or provisional-boundary failures abstain without a package |
| Public boundaries | Strict plugin, FastAPI `/v1/modules/M27-03/*`, and Typer `m27-03` adapter |

The module intentionally implements a metadata-only orchestration boundary. It does not open
containers, traverse external content, resolve identity or consent, inspect spectra or sequences,
infer proteins/proteoforms/isoforms, infer glioma biology, score complex activity, fuse all omics,
infer kinase activity, or make treatment recommendations. A workflow is executable only when every
node is deterministic and content-addressed, the DAG is acyclic and fully reachable, all seven
caller-declared controls are accepted/resolved/granted, and the request binds the provisional M27-02
media type.

## Contract closure

`WorkflowDAG` enforces unique node/edge IDs, unique endpoint pairs, known references, acyclicity,
entry reachability, and exit reachability. Requests enforce the exact M27-02 media type and unique
source IDs/digests. Executed results bind request, result, execution, and package IDs to the request
digest; all nodes must be completed; the package execution/environment digests must match; output and
result digests are canonical. Abstentions carry a safe-failure report, explicit reason, review state,
and no execution/package. Seven uncertainty dimensions are always present and are not-estimable for
orchestration metadata.

## Runtime and replay

The engine uses a stable node-ID topological order and hashes the seed, order, upstream digest,
container identities, policy, checkpoint selections, and environment declaration. It emits a typed
execution record and reproducible result package from those declarations. `verify(..., replay=True)`
re-executes the request and compares the complete canonical result; replay cannot be disabled
because a payload digest alone would accept a self-rehashed semantic mutation. JSON service and
plugin adapters parse strict JSON once; plugin execution requires an opaque validated token. API
and CLI errors are sanitized and CLI output refuses overwrite.

## Evidence commands

```text
python -m pytest --no-cov tests/contract/test_m27_03_provisional.py tests/modules/c27_complex_activity/test_m27_03_orchestrator.py -q
python -m evals.m27_03.run
python benchmarks/m27_03_reproducible_pipeline.py
```

The evaluator has five scenarios: supported execution, canonical replay, rejected-control
abstention, no-package safe failure, and plugin parity. The benchmark constructs one locked request
outside the timed loop and times ten complete public engine calls. Benchmarks are regression
tripwires, not scientific evidence.

## Claims ceiling

The output is a reproducible technical execution envelope only. It is not evidence of observed
complex activity, protein identity, proteoform or isoform identity, abundance, glioma-specific
biology, clinical validity, or treatment utility. All external artifacts and all biological meaning
remain owned by upstream authorities and require independent governed review.
