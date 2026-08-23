# M26/M27 result-envelope transport closure

The current M26 and M27 verification APIs declare a larger result envelope than
their ordinary request envelope. Their transport middleware and strict parsers
must therefore select the result ceiling for paths ending in `/verify`.

This closure applies the declared result ceiling to the M26-01 through M26-08
and M27-03 through M27-06 API surfaces. M26-02, M26-03, M26-04, M26-05,
M27-03, M27-04, M27-05, and M27-06 also now pass the result ceiling into their strict
JSON parser or bounded reader instead of falling back to the ordinary request
or global JSON limit.

The regression matrix in
`tests/deployment/test_model_api_transport.py` sends one syntactically valid
JSON body larger than each surface's request ceiling but smaller than its
declared result ceiling to `/verify`. Each route reaches result parsing and
returns a contract-level `422`, rather than being rejected prematurely as an
oversized ordinary request. The matrix currently covers twelve concrete API
factories. It also verifies that every surface rejects a non-JSON media type
with `415` before parsing.

```text
uv run pytest -o addopts='' tests/deployment/test_model_api_transport.py --no-cov
```
