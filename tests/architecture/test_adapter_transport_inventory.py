"""Keep every exposed standalone adapter behind transport admission."""

from __future__ import annotations

import ast
from pathlib import Path

ADAPTER_ROOT = Path(__file__).parents[2] / "src" / "glio_proteogen" / "adapters"


def test_every_standalone_fastapi_adapter_installs_request_size_middleware() -> None:
    missing: list[str] = []
    for path in sorted(ADAPTER_ROOT.glob("m*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        has_fastapi = any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "FastAPI"
            for node in ast.walk(tree)
        )
        if not has_fastapi:
            continue
        has_middleware = any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_middleware"
            and any(
                isinstance(argument, ast.Name) and argument.id == "RequestSizeLimitMiddleware"
                for argument in node.args
            )
            for node in ast.walk(tree)
        )
        if not has_middleware:
            missing.append(path.name)
    assert not missing, f"standalone FastAPI adapters without transport admission: {missing}"
