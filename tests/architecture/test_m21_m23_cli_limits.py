"""Architecture guards for bounded M21--M23 CLI artifact ingestion."""

from __future__ import annotations

from pathlib import Path

_EXPECTED_CLI_COUNT = 23


def test_m21_m23_clis_bound_file_reads_before_parsing() -> None:
    source_root = Path(__file__).resolve().parents[2] / "src" / "glio_proteogen" / "modules"
    cli_files = sorted(
        path
        for path in source_root.rglob("cli.py")
        if any(part.startswith(("m21_", "m22_", "m23_")) for part in path.parts)
    )

    assert len(cli_files) == _EXPECTED_CLI_COUNT
    for path in cli_files:
        source = path.read_text(encoding="utf-8")
        assert "read_bounded" in source, path
        assert "path.read_bytes()" not in source, path


def test_m21_m23_apis_bound_json_before_validation() -> None:
    source_root = Path(__file__).resolve().parents[2] / "src" / "glio_proteogen" / "modules"
    api_files = sorted(
        path
        for path in source_root.rglob("api.py")
        if any(part.startswith(("m21_", "m22_", "m23_")) for part in path.parts)
    )

    assert len(api_files) == _EXPECTED_CLI_COUNT
    for path in api_files:
        source = path.read_text(encoding="utf-8")
        assert "max_bytes=" in source, path
        assert "strict_json_loads(body)" not in source, path
