"""Resource ceilings for provisional M06/M07 standalone CLI adapters."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from glio_proteogen.adapters import m0608, m0703, m0704, m0708
from glio_proteogen.adapters.limits import RequestBodyTooLargeError, read_bounded

_MAX_JSON_BYTES = 4 * 1024 * 1024


@pytest.mark.parametrize(
    ("app", "module_name"),
    [
        (m0608.m0608_app, "m0608.py"),
        (m0703.m0703_app, "m0703.py"),
        (m0704.m0704_app, "m0704.py"),
        (m0708.m0708_app, "m0708.py"),
    ],
)
def test_standalone_cli_rejects_sparse_oversized_input(
    tmp_path: Path,
    app: Any,
    module_name: str,
) -> None:
    path = tmp_path / "oversized.json"
    with path.open("wb") as stream:
        stream.seek(_MAX_JSON_BYTES)
        stream.write(b"x")
    result = CliRunner().invoke(app, ["validate", str(path)])
    assert result.exit_code != 0, module_name
    assert "byte" in result.output.lower() or "rejected" in result.output.lower()


def test_standalone_cli_adapters_use_bounded_path_reads() -> None:
    root = Path(__file__).parents[2] / "src" / "glio_proteogen" / "adapters"
    for name in ("m0608.py", "m0703.py", "m0704.py", "m0708.py"):
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        assert not any(
            isinstance(node, ast.Attribute) and node.attr in {"read", "read_bytes"}
            for node in ast.walk(tree)
        ), name


def test_bounded_reader_raises_before_json_parse(tmp_path: Path) -> None:
    path = tmp_path / "oversized.json"
    with path.open("wb") as stream:
        stream.seek(_MAX_JSON_BYTES)
        stream.write(b"x")
    with pytest.raises(RequestBodyTooLargeError):
        read_bounded(path, _MAX_JSON_BYTES)
