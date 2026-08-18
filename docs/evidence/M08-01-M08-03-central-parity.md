# M08-01/M08-03 central interface parity

## Scope

The M08 transcript/protein modules already had contract, service, plugin, lifecycle,
and evaluator implementations, but their public central adapters were absent. This
slice closes that reachability gap without changing either provisional module ABI.

| Module | Schema route | Execution route | CLI group and command |
| --- | --- | --- | --- |
| M08-01 | `GET /v1/contracts/M08-01/{name}/schema` | `POST /v1/modules/M08-01/formal-state-validation` | `transcript-protein-state validate` |
| M08-03 | `GET /v1/contracts/M08-03/{name}/schema` | `POST /v1/modules/M08-03/baseline-estimate` | `protein-subtype-baseline estimate` |

Both groups also expose `export-schema` for every contract name in the module's
declared schema order. FastAPI and Typer use the same strict Pydantic adapters and
module validators, so the request is decoded once, bounded by the module's canonical
request ceiling, and rejected before model traversal when one of the seven control
decisions is unsafe. Validation errors are sanitized; duplicate JSON keys, wrong
media types, malformed JSON, and existing output paths fail closed.

## Evidence

- The focused M08-01/M08-03 interface suite passes 8/8.
- The complete M08 interface suite passes 37/37 (M08-01 through M08-08).
- Ruff check and format, strict MyPy on both central adapters, compileall, and
  `git diff --check` pass.
- Result files are canonical JSON and are created with exclusive-open semantics, so
  a CLI invocation cannot silently overwrite an existing artifact.

The modules remain explicitly provisional and retain their existing non-inference
claims ceilings; this change only makes their already-reviewed behavior reachable
through the central transport surfaces.
