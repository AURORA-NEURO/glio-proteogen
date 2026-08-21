"""Central CLI registration invariants."""

from __future__ import annotations

import ast
from pathlib import Path


def test_top_level_typer_group_names_are_unique() -> None:
    source = Path("src/glio_proteogen/adapters/cli.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "add_typer":
            continue
        for keyword in node.keywords:
            if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                assert isinstance(keyword.value.value, str)
                names.append(keyword.value.value)
    assert names
    assert len(names) == len(set(names)), sorted(
        name for name in set(names) if names.count(name) > 1
    )
