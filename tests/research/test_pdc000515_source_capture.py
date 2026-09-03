from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

import pytest

from tools import capture_pdc000515_source_manifest as capture
from tools import import_kncc_longitudinal_phospho as importer

if TYPE_CHECKING:
    from pathlib import Path

_SOURCE_CHANGED = "source changed during capture"


def _graphql_fixture(query: str) -> dict[str, object]:
    fixtures: dict[str, dict[str, object]] = {
        importer.PDC_STUDY_CATALOG_QUERY: {"studyCatalog": [{"versions": []}]},
        importer.PDC_VERSIONED_STUDY_QUERY: {"study": [{"filesCount": []}]},
        importer.PDC_VERSIONED_BIOSPECIMEN_QUERY: {"biospecimenPerStudy": []},
        importer.PDC_VERSIONED_FILES_QUERY: {"filesPerStudy": []},
        importer.PDC_VERSIONED_PROTOCOL_QUERY: {"protocolPerStudy": []},
        importer.PDC_EXPERIMENTAL_DESIGN_QUERY: {"studyExperimentalDesign": []},
    }
    return fixtures[query]


def test_capture_reverifies_local_files_immediately_before_private_write(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source_dir = tmp_path / "private-source"
    source_dir.mkdir()
    destination = source_dir / importer.PDC_SOURCE_MANIFEST_FILENAME
    verification_calls: list[Path] = []

    def verify(path: Path) -> dict[str, Path]:
        verification_calls.append(path)
        return {}

    monkeypatch.setattr(capture, "verify_source_files", verify)
    monkeypatch.setattr(capture, "_post", _graphql_fixture)

    manifest = capture.capture(source_dir, destination)

    assert verification_calls == [source_dir, source_dir]
    assert destination.read_bytes() == importer._canonical_bytes(manifest)
    parsed = cast("dict[str, object]", json.loads(destination.read_bytes()))
    assert parsed["schema_version"] == importer.PDC_SOURCE_MANIFEST_SCHEMA


def test_capture_rejects_a_destination_outside_the_private_source_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source_dir = tmp_path / "private-source"
    source_dir.mkdir()
    called = False

    def verify(_path: Path) -> dict[str, Path]:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(capture, "verify_source_files", verify)

    with pytest.raises(ValueError, match="must be written beside"):
        capture.capture(source_dir, tmp_path / "public" / "manifest.json")

    assert called is False


def test_capture_emits_nothing_when_the_closing_source_verification_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source_dir = tmp_path / "private-source"
    source_dir.mkdir()
    destination = source_dir / importer.PDC_SOURCE_MANIFEST_FILENAME
    call_count = 0

    def verify(_path: Path) -> dict[str, Path]:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise ValueError(_SOURCE_CHANGED)
        return {}

    monkeypatch.setattr(capture, "verify_source_files", verify)
    monkeypatch.setattr(capture, "_post", _graphql_fixture)

    with pytest.raises(ValueError, match="changed during capture"):
        capture.capture(source_dir, destination)

    assert call_count == 2
    assert not destination.exists()
