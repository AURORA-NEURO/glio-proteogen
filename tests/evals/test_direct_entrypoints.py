"""Static guardrails for repository-root evaluator entrypoints."""

from __future__ import annotations

import re
from pathlib import Path

_EVALS_ROOT = Path(__file__).resolve().parents[2] / "evals"
_DIRECT_ENTRYPOINTS = tuple(
    sorted((*_EVALS_ROOT.glob("m*/benchmark.py"), *_EVALS_ROOT.glob("m*/run.py")))
)
_BOOTSTRAP = "sys.path.insert(0, str("
def test_all_evaluator_entrypoints_bootstrap_repository_root() -> None:
    """Every script must work when launched by file path from the repository root."""

    assert _DIRECT_ENTRYPOINTS, "evaluator entrypoint discovery unexpectedly returned no scripts"
    for path in _DIRECT_ENTRYPOINTS:
        source = path.read_text(encoding="utf-8")
        assert _BOOTSTRAP in source, path
        assert "Path(__file__)" in source, path
        assert (
            '__package__ in {None, ""}' in source
            or "__package__ in (None, \"\")" in source
            or "if not __package__" in source
        ), path
        assert not re.search(r"^from " + r"\.", source, re.MULTILINE), path
