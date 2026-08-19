"""Static guardrails for directly executable package CLI modules."""

from __future__ import annotations

import re
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
_DIRECT_SOURCES = tuple(
    sorted(
        path for path in _SRC_ROOT.rglob("*.py") if "__main__" in path.read_text(encoding="utf-8")
    )
)
def test_direct_package_entrypoints_bootstrap_src_root() -> None:
    """File-path execution must resolve the package and package-local imports."""

    assert _DIRECT_SOURCES, "direct package entrypoint discovery unexpectedly returned no modules"
    for path in _DIRECT_SOURCES:
        source = path.read_text(encoding="utf-8")
        assert "sys.path.insert(0, str(_SOURCE_ROOT))" in source, path
        assert '__package__ in {None, ""}' in source, path
        assert not re.search(r"^from " + r"\.", source, re.MULTILINE), path
