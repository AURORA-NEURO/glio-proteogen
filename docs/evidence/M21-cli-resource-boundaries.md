# M21 CLI resource-boundary hardening

The M21-01 through M21-08 Typer adapters accept request and result paths. Before this fix,
each adapter called `Path.read_bytes()` and only then applied the contract byte ceiling during
JSON parsing. A hostile local path could therefore allocate an arbitrarily large file before the
declared request/result limit was enforced.

All eight adapters now use the shared `read_bounded` transport primitive with their exact
contract-owned request and result ceilings. The primitive reads at most `limit + 1` bytes and
raises before JSON or Pydantic parsing. This preserves the provisional M21 schemas and result
semantics while making CLI resource behavior match the bounded HTTP/plugin boundaries.

The adversarial matrix covers both request and result readers for M21-01, M21-02, M21-03,
M21-04, M21-05, M21-06, M21-07, and M21-08, plus a monkeypatched guard proving none calls
unbounded `Path.read_bytes()`.

Validation evidence from the current-main build:

- 154 M21 tests passed, including 17 resource-boundary adversarial cases.
- Ruff, format, strict MyPy (9 touched files), and compileall passed.
- All eight M21 evaluator entrypoints passed (72 declared evaluator checks).
- Two `SOURCE_DATE_EPOCH=315532800` builds were byte-identical: wheel 3,867,423 bytes,
  SHA-256 `767235690f7b60c26cfa74eeb87a22efe748ca43c93656d397bfa7dea4f0c508`; sdist
  4,530,315 bytes, SHA-256 `6db8ca1cd01b7970ef9644e534afc73802ea2e76944ad77bd739fdb06b58e446`.
