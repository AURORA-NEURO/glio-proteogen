# M27-03 package/release evidence

The release lane used Hatchling `1.31.0` through `uv build`, with both build outputs written
outside the repository. Two clean builds produced byte-identical artifacts:

| Artifact | Size | Reproducibility result |
| --- | ---: | --- |
| `glio_proteogen-0.1.0-py3-none-any.whl` | 1,033,595 bytes | identical across two builds |
| `glio_proteogen-0.1.0.tar.gz` | 1,534,334 bytes | identical across two builds |

The wheel installed into an isolated target with `uv pip install --target ... --no-deps`; the
isolated import gate loaded `glio_proteogen`, `GLIO-PROTEOGEN-M27-03`, and the M27-03 engine.
The build output directories were deliberately external so generated artifacts could not become
inputs to a subsequent sdist. This is a release reproducibility requirement, not a scientific
validation claim.

```text
uv build --out-dir <external-output-a>
uv build --out-dir <external-output-b>
uv pip install --target <external-install> <wheel> --no-deps
```

The release lane does not claim a frozen ABI: M27-03 remains `0.1.0-provisional`, and package
installation does not confer owner approval or biological validity.
