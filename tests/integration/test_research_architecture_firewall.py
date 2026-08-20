"""Keep research computation isolated from governed module and transport surfaces."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as central_cli

if TYPE_CHECKING:
    from collections.abc import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPO_ROOT / "src" / "glio_proteogen"
GOVERNED_ROOTS = (
    SOURCE_ROOT / "modules" / "c03_proteomics",
    SOURCE_ROOT / "modules" / "c04_proteoform",
    SOURCE_ROOT / "modules" / "c05_ptm_localization",
    SOURCE_ROOT / "adapters",
)
RESEARCH_NAMESPACE = "glio_proteogen.research"


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def _is_research_module(module: str) -> bool:
    return module == RESEARCH_NAMESPACE or module.startswith(RESEARCH_NAMESPACE + ".")


def test_governed_source_never_imports_research_namespace() -> None:
    """Research primitives remain additive and cannot become governed dependencies."""

    violations: list[str] = []
    for root in GOVERNED_ROOTS:
        for path in root.rglob("*.py"):
            imported = _imported_modules(path)
            if any(_is_research_module(module) for module in imported):
                violations.append(str(path.relative_to(REPO_ROOT)))
    assert violations == []


def test_central_surfaces_do_not_expose_research_execution(tmp_path: Path) -> None:
    """The central transports expose governed contracts, never research execution."""

    app = create_app(tmp_path / "events.sqlite")
    route_paths = {str(getattr(route, "path", "")).lower() for route in app.routes}
    assert not any("research" in path for path in route_paths)
    assert not any("proteomics/search" in path for path in route_paths)

    command_names = _registered_names(central_cli.registered_commands)
    group_names = _registered_names(central_cli.registered_groups)
    assert "research" not in command_names | group_names
    assert "proteomics-search" not in command_names | group_names


def _registered_names(items: Iterable[object]) -> set[str]:
    return {str(getattr(item, "name", "")).lower() for item in items}
