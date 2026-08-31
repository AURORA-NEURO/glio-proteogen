from __future__ import annotations

import hashlib
import json
import zipfile
from typing import TYPE_CHECKING

import pytest

from tools import capture_cptac_gbm_supplements as capture

if TYPE_CHECKING:
    from pathlib import Path

_CLOSING_VERIFICATION_ERROR = "source changed during closing verification"


def _workbook(path: Path, dimensions: tuple[tuple[str, str], ...]) -> None:
    sheets = "".join(
        f'<sheet name="{name}" sheetId="{index}" r:id="rId{index}"/>'
        for index, (name, _dimension) in enumerate(dimensions, start=1)
    )
    relationships = "".join(
        '<Relationship '
        f'Id="rId{index}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
        'relationships/worksheet" '
        f'Target="worksheets/sheet{index}.xml"/>'
        for index, _item in enumerate(dimensions, start=1)
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f"<sheets>{sheets}</sheets></workbook>",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f"{relationships}</Relationships>",
        )
        for index, (_name, dimension) in enumerate(dimensions, start=1):
            archive.writestr(
                f"xl/worksheets/sheet{index}.xml",
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f'<dimension ref="{dimension}"/><sheetData/></worksheet>',
            )


def _lock(
    path: Path,
    label: str,
    dimensions: tuple[tuple[str, str], ...],
) -> capture.SupplementLock:
    return capture.SupplementLock(
        label=label,
        official_filename=f"{label}.xlsx",
        bytes=path.stat().st_size,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        source_url=f"https://example.test/{label}.xlsx",
        sheet_dimensions=dimensions,
    )


def test_bounded_workbook_inventory_preserves_exact_sheet_order(tmp_path: Path) -> None:
    source = tmp_path / "source.xlsx"
    dimensions = (("README", "A1:C5"), ("matrix", "A1:Z101"))
    _workbook(source, dimensions)

    assert capture._workbook_dimensions(source) == dimensions


def test_exact_source_verification_rejects_content_drift(tmp_path: Path) -> None:
    source = tmp_path / "source.xlsx"
    dimensions = (("README", "A1:C5"),)
    _workbook(source, dimensions)
    lock = _lock(source, "fixture", dimensions)
    capture._verify_source(source, lock)

    source.write_bytes(source.read_bytes() + b"drift")

    with pytest.raises(ValueError, match="byte length"):
        capture._verify_source(source, lock)


def test_capture_emits_only_cell_free_public_structure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    table_s2 = tmp_path / "private-s2.xlsx"
    table_s3 = tmp_path / "private-s3.xlsx"
    s2_dimensions = (("README", "A1:C17"), ("proteome", "A1:DH10999"))
    s3_dimensions = (("README", "A1:C5"), ("calls", "A1:E8259"))
    _workbook(table_s2, s2_dimensions)
    _workbook(table_s3, s3_dimensions)
    monkeypatch.setattr(capture, "TABLE_S2_LOCK", _lock(table_s2, "table_s2", s2_dimensions))
    monkeypatch.setattr(capture, "TABLE_S3_LOCK", _lock(table_s3, "table_s3", s3_dimensions))
    destination = tmp_path / "safe" / "receipt.json"

    receipt = capture.capture(table_s2, table_s3, destination)

    assert destination.read_bytes() == capture._canonical_bytes(receipt)
    parsed = json.loads(destination.read_bytes())
    assert parsed["schema_version"] == capture.SOURCE_LOCK_SCHEMA
    assert parsed["privacy"] == {
        "identifier_derived_digests_emitted": False,
        "patient_identifiers_emitted": False,
        "sample_headers_emitted": False,
        "worksheet_cells_emitted": False,
    }
    serialized = destination.read_text(encoding="utf-8")
    assert str(tmp_path) not in serialized
    assert "private-s2" not in serialized
    assert "private-s3" not in serialized


def test_capture_writes_nothing_when_closing_verification_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = 0

    def verify(_path: Path, _lock: capture.SupplementLock) -> None:
        nonlocal calls
        calls += 1
        if calls == 4:
            raise ValueError(_CLOSING_VERIFICATION_ERROR)

    monkeypatch.setattr(capture, "_verify_source", verify)
    destination = tmp_path / "receipt.json"

    with pytest.raises(ValueError, match="closing verification"):
        capture.capture(tmp_path / "s2.xlsx", tmp_path / "s3.xlsx", destination)

    assert calls == 4
    assert not destination.exists()


def test_workbook_inventory_rejects_missing_dimensions(tmp_path: Path) -> None:
    source = tmp_path / "source.xlsx"
    _workbook(source, (("README", ""),))

    with pytest.raises(ValueError, match="omitted its bounded dimension"):
        capture._workbook_dimensions(source)
