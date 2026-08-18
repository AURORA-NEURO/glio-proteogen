"""Architecture guards for the additive, non-governed research namespace.

The research pipeline is intentionally useful without becoming an accidental
implementation of a frozen M03/M04/M05 contract.  These tests make that
boundary executable: governed module code and the shared adapters may not
import the research namespace, and the public application may not expose a
research execution route.
"""

from __future__ import annotations

import ast
from pathlib import Path

from glio_proteogen.adapters.api import create_app

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _REPO_ROOT / "src" / "glio_proteogen"
_GOVERNED_ROOTS = (
    _SRC_ROOT / "modules" / "c03_protein_inference",
    _SRC_ROOT / "modules" / "c04_proteoform_isoform",
    _SRC_ROOT / "modules" / "c05_ptm_localization",
)
_SHARED_ADAPTERS = (
    _SRC_ROOT / "adapters" / "api.py",
    _SRC_ROOT / "adapters" / "cli.py",
)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def test_governed_modules_and_adapters_cannot_import_research_namespace() -> None:
    """Prevent research computation from becoming a governed dependency."""

    paths = [file for root in (*_GOVERNED_ROOTS,) for file in root.rglob("*.py")] + list(
        _SHARED_ADAPTERS
    )
    violations = {
        str(path.relative_to(_REPO_ROOT)): module
        for path in paths
        for module in _imported_modules(path)
        if module == "glio_proteogen.research" or module.startswith("glio_proteogen.research.")
    }
    assert violations == {}


def test_public_fastapi_routes_have_no_research_execution_surface(tmp_path: Path) -> None:
    """The shared API may expose governed contracts, never research execution."""

    application = create_app(tmp_path / "events.sqlite3")
    violations: list[str] = []
    for route in application.routes:
        path = getattr(route, "path", "")
        endpoint = getattr(route, "endpoint", None)
        endpoint_module = getattr(endpoint, "__module__", "")
        if "research" in path.lower() or endpoint_module.startswith("glio_proteogen.research"):
            violations.append(f"{path}:{endpoint_module}")
    assert violations == []
