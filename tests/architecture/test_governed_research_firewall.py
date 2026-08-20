"""Architecture-level firewall for governed C03/C04/C05 surfaces.

The research package is intentionally additive and non-governed.  The frozen
M03/M04/M05 contracts and their C03/C04/C05 implementation families must
therefore remain unable to import or expose it by accident, even as the
central adapters grow.  These checks inspect the source graph and the
assembled transports rather than relying only on individual module tests; a
copied route, a new import, or a nested CLI registration is consequently
visible at the boundary where it would become public.
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
_GOVERNED_FAMILY_GLOBS: Final = (
    "modules/c03_*",
    "modules/c04_*",
    "modules/c05_*",
    "contracts/m03_*",
    "contracts/m04_*",
    "contracts/m05_*",
)
_FROZEN_MANIFEST_MODULES: Final = {
    *(f"M03-{index:02d}" for index in range(1, 9)),
    *(f"M04-{index:02d}" for index in range(1, 9)),
    *(f"M05-{index:02d}" for index in range(1, 5)),
}
_RESEARCH_CAPABILITY_MARKERS: Final = (
    "/research",
    "research",
    "spectrum",
    "mzml",
    "psm",
    "fdr",
    "q-value",
    "qvalue",
    "quantification",
    "protein-groups",
    "protein_groups",
    "peptide-spectrum",
    "target-decoy",
    "target_decoy",
    "cohort",
)


def _governed_python_files() -> Iterator[Path]:
    """Yield every tracked C03/C04/C05 source file, including nested helpers.

    The previous guard discovered only ``contracts/m03_01``-style folders and
    silently missed the implementation families, which live below
    ``modules/c03_*``.  Keep the inventory explicit and deterministic so a
    newly added family cannot fall outside the AST firewall unnoticed.
    """

    paths: set[Path] = set()
    for pattern in _GOVERNED_FAMILY_GLOBS:
        for family_root in _SOURCE_ROOT.glob(pattern):
            if family_root.is_dir():
                paths.update(family_root.rglob("*.py"))

    # Central adapters are governed transport composition, not research code.
    paths.update(
        {
            _SOURCE_ROOT / "adapters" / "api.py",
            _SOURCE_ROOT / "adapters" / "cli.py",
        }
    )
    yield from sorted(paths)


def _family_roots() -> tuple[Path, ...]:
    """Return the implementation families covered by the source inventory."""

    return tuple(
        sorted(
            family_root
            for pattern in _GOVERNED_FAMILY_GLOBS[:3]
            for family_root in _SOURCE_ROOT.glob(pattern)
            if family_root.is_dir()
        )
    )


@pytest.mark.contract
def test_governed_family_inventory_is_complete() -> None:
    """The firewall must see all three governed implementation families."""

    family_roots = _family_roots()
    assert tuple(path.name[:3] for path in family_roots) == ("c03", "c04", "c05")
    assert all(tuple(path.rglob("*.py")) for path in family_roots)


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
    """Walk all Typer nesting levels, including future nested sub-groups."""

    def walk(typer_app: object, prefix: str, seen: set[int]) -> Iterator[tuple[str, object]]:
        app_id = id(typer_app)
        if app_id in seen:
            return
        seen.add(app_id)
        for command in getattr(typer_app, "registered_commands", ()):
            callback = getattr(command, "callback", None)
            if callback is not None:
                name = getattr(command, "name", None) or "<root>"
                yield f"{prefix} {name}".strip(), callback
        for group in getattr(typer_app, "registered_groups", ()):
            child = getattr(group, "typer_instance", None)
            if child is not None:
                name = getattr(group, "name", None) or "<group>"
                yield from walk(child, f"{prefix} {name}".strip(), seen)

    yield from walk(cli_app, "", set())


@pytest.mark.contract
def test_central_cli_has_no_research_execution_or_research_owned_callbacks() -> None:
    """The central CLI may serve the API but cannot execute research operations."""

    callbacks = tuple(_registered_cli_callbacks())
    assert callbacks, "central CLI callback inventory unexpectedly empty"
    for name, callback in callbacks:
        module = _callback_module(callback)
        assert module is not None, (name, module)
        assert module.startswith(("glio_proteogen.adapters.", "glio_proteogen.modules.")), (
            name,
            module,
        )
        assert not module.startswith(_RESEARCH_NAMESPACE), (name, module)
        assert not any(token in name.lower() for token in _RESEARCH_CAPABILITY_MARKERS), name


def _route_inventory() -> tuple[tuple[str, str, str, str], ...]:
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
            routes.append(
                (
                    path,
                    methods,
                    _callback_module(endpoint) or "",
                    getattr(endpoint, "__qualname__", getattr(endpoint, "__name__", "")),
                )
            )
        return tuple(routes)


@pytest.mark.contract
def test_central_api_route_inventory_has_no_research_execution_surface() -> None:
    """No public route may masquerade as spectrum/cohort/research execution."""

    routes = _route_inventory()
    assert routes, "central API route inventory unexpectedly empty"
    for path, methods, module, qualname in routes:
        public_metadata = f"{path} {methods} {module} {qualname}".lower()
        assert not any(token in public_metadata for token in _RESEARCH_CAPABILITY_MARKERS), (
            path,
            methods,
            module,
            qualname,
        )
        if module.startswith("glio_proteogen"):
            assert module == "glio_proteogen.adapters.api", (path, module)


@pytest.mark.contract
def test_central_openapi_inventory_has_no_research_capability_aliases() -> None:
    """Operation IDs and summaries cannot smuggle research execution public."""

    with (
        TemporaryDirectory(prefix="glio-governed-firewall-openapi-") as temporary,
        TestClient(create_app(Path(temporary) / "events.sqlite")) as client,
    ):
        document = client.get("/openapi.json").json()
    paths = document.get("paths")
    assert isinstance(paths, dict)
    assert paths
    exposed: list[str] = []
    for path, operations in paths.items():
        if not isinstance(operations, dict):
            continue
        for method, operation in operations.items():
            if not isinstance(operation, dict):
                continue
            metadata = " ".join(
                str(operation.get(field, ""))
                for field in ("operationId", "summary", "description", "tags")
            )
            haystack = f"{path} {method} {metadata}".lower()
            if any(marker in haystack for marker in _RESEARCH_CAPABILITY_MARKERS):
                exposed.append(haystack)
    assert not exposed, "research capability leaked into OpenAPI inventory: " + "; ".join(exposed)


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
