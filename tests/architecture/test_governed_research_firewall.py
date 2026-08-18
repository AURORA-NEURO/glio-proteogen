"""Architecture-level firewall for governed M03/M04/M05 surfaces.

The research package is intentionally additive and non-governed.  The frozen
M03/M04/M05 contracts must therefore remain unable to import or expose it by
accident, even as the central adapters grow.  These checks inspect the source
graph and the assembled transports rather than relying only on individual
module tests; a copied route or a new import is consequently visible at the
boundary where it would become public.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Final, cast

import pytest
from fastapi.testclient import TestClient

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app

if TYPE_CHECKING:
    from collections.abc import Iterator

    from fastapi import FastAPI

pytestmark = pytest.mark.contract

_REPO_ROOT: Final = Path(__file__).resolve().parents[2]
_SOURCE_ROOT: Final = _REPO_ROOT / "src" / "glio_proteogen"
_RESEARCH_NAMESPACE: Final = "glio_proteogen.research"
_GOVERNED_COMPONENTS: Final = ("contracts", "modules")
_FROZEN_MODULES: Final = {
    *(f"M03-{index:02d}" for index in range(1, 9)),
    *(f"M04-{index:02d}" for index in range(1, 9)),
    *(f"M05-{index:02d}" for index in range(1, 6)),
}
_FROZEN_MANIFEST_MODULES: Final = {
    *(f"M03-{index:02d}" for index in range(1, 9)),
    *(f"M04-{index:02d}" for index in range(1, 9)),
    *(f"M05-{index:02d}" for index in range(1, 5)),
}
_RESEARCH_ROUTE_TOKENS: Final = (
    "/research",
    "spectrum",
    "mzml",
    "psm",
    "fdr",
    "quantification",
    "protein-groups",
    "cohort",
)


def _governed_python_files() -> Iterator[Path]:
    """Yield every frozen M03/M04/M05 source file, including nested helpers."""

    for component in _GOVERNED_COMPONENTS:
        component_root = _SOURCE_ROOT / component
        for module_path in component_root.glob("m??_??"):
            module_id = module_path.name.upper().replace("_", "-")
            if module_id in _FROZEN_MODULES:
                yield from module_path.rglob("*.py")

    # Central adapters are governed transport composition, not research code.
    yield _SOURCE_ROOT / "adapters" / "api.py"
    yield _SOURCE_ROOT / "adapters" / "cli.py"


def _import_targets(tree: ast.AST) -> Iterator[tuple[str, int]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from ((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            yield node.module, node.lineno


@pytest.mark.parametrize("source_path", tuple(_governed_python_files()))
def test_frozen_governed_source_cannot_import_research_namespace(source_path: Path) -> None:
    """Reject direct and aliased imports that would make research governed."""

    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    violations = [
        f"{source_path.relative_to(_REPO_ROOT)}:{line}: {module}"
        for module, line in _import_targets(tree)
        if module == _RESEARCH_NAMESPACE or module.startswith(f"{_RESEARCH_NAMESPACE}.")
    ]
    assert not violations, "research namespace crossed governed boundary: " + "; ".join(violations)


def _callback_module(callback: object) -> str | None:
    return getattr(callback, "__module__", None)


def _registered_cli_callbacks() -> Iterator[tuple[str, object]]:
    for command in cli_app.registered_commands:
        if command.callback is not None:
            yield command.name or "<root>", command.callback
    for group in cli_app.registered_groups:
        typer_app = group.typer_instance
        if typer_app is None:
            continue
        for command in typer_app.registered_commands:
            if command.callback is not None:
                name = f"{group.name or '<group>'} {command.name or '<root>'}"
                yield name, command.callback


@pytest.mark.contract
def test_central_cli_has_no_research_execution_or_research_owned_callbacks() -> None:
    """The central CLI may serve the API but cannot execute research operations."""

    callbacks = tuple(_registered_cli_callbacks())
    assert callbacks, "central CLI callback inventory unexpectedly empty"
    for name, callback in callbacks:
        module = _callback_module(callback)
        assert module is not None, (name, module)
        assert module.startswith("glio_proteogen.adapters."), (name, module)
        assert not module.startswith(_RESEARCH_NAMESPACE), (name, module)
        assert not any(token in name.lower() for token in _RESEARCH_ROUTE_TOKENS), name


def _route_inventory() -> tuple[tuple[str, str, str], ...]:
    with (
        TemporaryDirectory(prefix="glio-governed-firewall-") as temporary,
        TestClient(create_app(Path(temporary) / "events.sqlite")) as client,
    ):
        application = cast("FastAPI", client.app)
        routes = []
        for route in application.routes:
            path = getattr(route, "path", None)
            endpoint = getattr(route, "endpoint", None)
            if not isinstance(path, str) or endpoint is None:
                continue
            methods = ",".join(sorted(getattr(route, "methods", ())))
            routes.append((path, methods, _callback_module(endpoint) or ""))
        return tuple(routes)


@pytest.mark.contract
def test_central_api_route_inventory_has_no_research_execution_surface() -> None:
    """No public route may masquerade as spectrum/cohort/research execution."""

    routes = _route_inventory()
    assert routes, "central API route inventory unexpectedly empty"
    for path, methods, module in routes:
        normalized = path.lower()
        assert not any(token in normalized for token in _RESEARCH_ROUTE_TOKENS), (
            path,
            methods,
        )
        if module.startswith("glio_proteogen"):
            assert module == "glio_proteogen.adapters.api", (path, module)


@pytest.mark.contract
def test_central_api_import_does_not_load_research_execution_modules() -> None:
    """Transport composition must remain independent of research implementation."""

    # Run in a fresh interpreter because another test file may already have
    # imported the research package in this process.  PYTHONPATH is explicit so
    # this checks the checkout rather than an installed wheel from another ref.
    script = (
        "import sys; "
        "import glio_proteogen.adapters.api; "
        "assert not any(name == 'glio_proteogen.research' or "
        "name.startswith('glio_proteogen.research.') for name in sys.modules)"
    )
    result = subprocess.run(  # noqa: S603 - executable is the current test interpreter.
        [sys.executable, "-c", script],
        cwd=_REPO_ROOT,
        env={**os.environ, "PYTHONPATH": str(_SOURCE_ROOT)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


@pytest.mark.contract
def test_frozen_manifests_keep_research_claims_outside_governed_ceiling() -> None:
    """Manifest text remains explicit about the non-inference ceiling."""

    manifests = tuple(
        path
        for path in (_REPO_ROOT / "docs" / "modules").glob("M0[345]-*.manifest.md")
        if path.stem.split(".", maxsplit=1)[0] in _FROZEN_MANIFEST_MODULES
    )
    assert len(manifests) == len(_FROZEN_MANIFEST_MODULES)
    for manifest_path in manifests:
        text = manifest_path.read_text(encoding="utf-8").lower()
        assert "claims ceiling" in text, manifest_path
        assert "no" in text, manifest_path
        if manifest_path.name.startswith("M03-"):
            assert "protein inference" in text, manifest_path
        elif manifest_path.name.startswith("M04-"):
            assert "proteoform" in text, manifest_path
        else:
            assert "ptm" in text, manifest_path
        assert "research" not in text, (
            "governed manifest must not silently adopt research namespace claims",
            manifest_path,
        )
