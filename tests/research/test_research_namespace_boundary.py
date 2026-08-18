"""Architecture guard: research computation cannot leak into governed modules."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import cast

_ROOT = Path(__file__).resolve().parents[2]
_GOVERNED_ROOTS = (
    _ROOT / "src" / "glio_proteogen" / "modules",
    _ROOT / "src" / "glio_proteogen" / "adapters",
)


def _research_imports(path: Path) -> list[tuple[str, int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        line = cast("int", getattr(node, "lineno", 0))
        module = (
            node.module if isinstance(node, ast.ImportFrom) and node.module is not None else None
        )
        if isinstance(node, ast.Import):
            names = tuple(alias.name for alias in node.names)
            if any(
                name == "glio_proteogen.research" or name.startswith("glio_proteogen.research.")
                for name in names
            ):
                found.append((str(path), line))
        elif module == "glio_proteogen.research" or (
            module is not None and module.startswith("glio_proteogen.research.")
        ):
            found.append((str(path), line))
    return found


def test_governed_modules_and_adapters_do_not_import_research_namespace() -> None:
    offenders = [
        hit
        for root in _GOVERNED_ROOTS
        for path in root.rglob("*.py")
        for hit in _research_imports(path)
    ]
    assert offenders == []
