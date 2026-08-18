# M11 adapter file-resource boundaries

The standalone M11 adapters accept JSON request and result files through their
Typer paths. Before this change, eight adapters used `Path.read_bytes()` or an
equivalent unbounded path read even though each M11 contract already declared
canonical request and result ceilings. That allowed an oversized file to be
fully allocated before strict JSON rejection.

The path readers now use the shared `read_bounded` helper and pass the
contract-specific limit before parsing:

| adapters | request | result |
| --- | ---: | ---: |
| M11-01, M11-02, M11-03, M11-04 | 4 MiB | 8 MiB |
| M11-05, M11-06, M11-07, M11-08 | 4 MiB | 8 MiB |

M11-02 also preserves its existing HTTP request middleware. The adapter
changes do not alter schemas, operation names, media types, replay digests, or
the provisional ABI. They close only the path-based admission bypass and use
the declared result ceiling for CLI replay files and strict result parsing.

`tests/interfaces/test_m11_adapter_resource_limits.py` covers all eight
request readers, all eight result-reader paths, rejection before parsing, and
a `Path.read_bytes` firewall. Tests use small synthetic overflow files with a
patched limit so the regression does not allocate multi-megabyte fixtures.
