# M27-03 package/release evidence

The release lane used Hatchling `1.31.0` through `uv build`, with both build outputs written
outside the repository. Two clean builds produced byte-identical artifacts:

| Artifact | Size | Reproducibility result |
| --- | ---: | --- |
| `glio_proteogen-0.1.0-py3-none-any.whl` | 3,220,892 bytes; SHA256 `9a3f3a625091a59b8dedd93fb54962483ca345b81fa94c350532b3641cf2c5b2` | identical across two builds |
| `glio_proteogen-0.1.0.tar.gz` | 3,682,684 bytes; SHA256 `891d57788bfe75574cc880f3d7758566c922f3ad4e77f88cf17c1260839e0c97` | identical across two builds |

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
