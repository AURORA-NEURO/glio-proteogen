from __future__ import annotations

import ast
from pathlib import Path

import pytest
import typer

from glio_proteogen.adapters.limits import RequestBodyTooLargeError, read_bounded
from glio_proteogen.modules.c10_pathway_proteotype.m10_01_formal_state_feature_schema.cli import (
    _read as read_m1001,
)
from glio_proteogen.modules.c10_pathway_proteotype.m10_07_calibration_selective_prediction import (
    cli as m1007_cli,
)

read_m1007_request = m1007_cli._read_request
read_m1007_result = m1007_cli._read_object

_ROOT = Path(__file__).parents[1]
_C10_ADAPTERS = (
    _ROOT
    / "src"
    / "glio_proteogen"
    / "modules"
    / "c10_pathway_proteotype"
    / "m10_01_formal_state_feature_schema"
    / "cli.py",
    _ROOT
    / "src"
    / "glio_proteogen"
    / "modules"
    / "c10_pathway_proteotype"
    / "m10_02_representation_feature_constructor"
    / "interfaces.py",
    _ROOT
    / "src"
    / "glio_proteogen"
    / "modules"
    / "c10_pathway_proteotype"
    / "m10_03_mature_baseline_estimator"
    / "interfaces.py",
    _ROOT
    / "src"
    / "glio_proteogen"
    / "modules"
    / "c10_pathway_proteotype"
    / "m10_07_calibration_selective_prediction"
    / "cli.py",
)


def test_c10_path_adapters_use_bounded_reader_instead_of_read_bytes() -> None:
    for path in _C10_ADAPTERS:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        unbounded_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "read_bytes"
        ]
        assert not unbounded_calls, f"{path} contains an unbounded read_bytes call"
        assert "read_bounded" in path.read_text(encoding="utf-8")


def test_bounded_reader_rejects_before_consuming_oversized_file(tmp_path: Path) -> None:
    path = tmp_path / "oversized.json"
    path.write_bytes(b"{" + b"x" * 32)
    with pytest.raises(RequestBodyTooLargeError):
        read_bounded(path, max_bytes=32)


@pytest.mark.parametrize("reader", [read_m1001, read_m1007_request, read_m1007_result])
def test_c10_json_readers_reject_oversized_files_before_parsing(
    tmp_path: Path, reader: object
) -> None:
    path = tmp_path / "oversized.json"
    path.write_bytes(b"{" + b"x" * (4 * 1024 * 1024))
    with pytest.raises((typer.BadParameter, ValueError)):
        reader(path)  # type: ignore[operator]
