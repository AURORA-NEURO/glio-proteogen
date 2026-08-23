"""Regression coverage for the installed wheel deployment surface."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).parents[2]
WHEEL_GLOB = "glio_proteogen-*.whl"


@pytest.mark.package_artifact
def test_built_wheel_imports_asgi_and_all_module_families() -> None:
    wheels = sorted((REPOSITORY_ROOT / "dist").glob(WHEEL_GLOB))
    if not wheels:
        pytest.skip("build the wheel before running package-artifact tests")

    wheel = wheels[-1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(wheel)
    probe = (
        "import importlib, pkgutil, glio_proteogen; "
        "names=[m.name for m in pkgutil.walk_packages(glio_proteogen.__path__, "
        "glio_proteogen.__name__ + '.')]; "
        "[importlib.import_module(name) for name in names]; "
        "import glio_proteogen.asgi; "
        "assert glio_proteogen.asgi.app is not None; "
        "print(glio_proteogen.__file__); print('imported_modules=' + str(len(names)))"
    )
    result = subprocess.run(  # noqa: S603 - controlled local interpreter and probe.
        [sys.executable, "-c", probe],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert str(wheel) in result.stdout
    assert "imported_modules=" in result.stdout
