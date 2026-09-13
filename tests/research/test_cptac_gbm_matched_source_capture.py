from __future__ import annotations

import csv
import io
import json
from typing import TYPE_CHECKING, cast

import pytest

from tools import capture_cptac_gbm_matched_source_manifest as capture

if TYPE_CHECKING:
    from pathlib import Path


def _sample_map(prefix: str) -> bytes:
    fields = [
        "FileNameRegEx",
        "AnalyticalSample",
        "126C",
        "127N",
        "127C",
        "128N",
        "128C",
        "129N",
        "129C",
        "130N",
        "130C",
        "131N",
        "131C",
    ]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    for plex in range(11):
        row = dict.fromkeys(fields, "")
        row["AnalyticalSample"] = f"{prefix}{plex}"
        row["126C"] = "POOL"
        for index, channel in enumerate(fields[3:], start=1):
            row[channel] = f"CPT{plex:02d}{index:07d}"
        writer.writerow(row)
    return output.getvalue().encode()


def _biospecimen_rows() -> dict[str, list[dict[str, object]]]:
    rows: list[dict[str, object]] = []
    rows.append(
        {
            "aliquot_submitter_id": "ref",
            "case_id": "pool",
            "case_submitter_id": "pool",
            "sample_type": "Not Reported",
            "taxon": "Homo sapiens",
            "case_status": "Qualified",
        }
    )
    rows.extend(
        {
            "aliquot_submitter_id": f"CPT{index // 10:02d}{index % 10 + 1:07d}",
            "case_id": f"case-{index}",
            "case_submitter_id": f"case-{index}",
            "sample_type": "Primary Tumor" if index < 100 else "Solid Tissue Normal",
            "taxon": "Homo sapiens",
            "case_status": "Disqualified" if index == 0 else "Qualified",
        }
        for index in range(110)
    )
    return {"PDC000204": rows, "PDC000205": [dict(row) for row in rows]}


def test_parse_sample_map_filters_blank_tail_and_is_order_stable() -> None:
    labels, oracles = capture.parse_sample_map(_sample_map("P"))
    assert len(labels) == 110
    assert len(set(labels)) == 110
    assert oracles["rows"] == 11
    assert oracles["analytical_samples"] == 11
    assert oracles["channels"] == (
        "126C",
        "127N",
        "127C",
        "128N",
        "128C",
        "129N",
        "129C",
        "130N",
        "130C",
        "131N",
        "131C",
    )


def test_parse_sample_map_rejects_duplicate_aliquots() -> None:
    payload = _sample_map("P").replace(b"CPT000000002", b"CPT000000001", 1)
    with pytest.raises(ValueError, match="duplicate"):
        capture.parse_sample_map(payload)


def test_parse_sample_map_rejects_truncated_or_misplaced_pool_rows() -> None:
    truncated = _sample_map("P").replace(b"CPT000000010\n", b"\n", 1)
    with pytest.raises(ValueError, match="110"):
        capture.parse_sample_map(truncated)
    misplaced = _sample_map("P").replace(b"POOL\tCPT000000001", b"CPT000000000\tPOOL", 1)
    with pytest.raises(ValueError, match="reference"):
        capture.parse_sample_map(misplaced)


def test_matched_biospecimens_require_identical_case_metadata() -> None:
    rows = _biospecimen_rows()
    rows["PDC000205"][1]["case_id"] = "different"
    labels = [
        str(row["aliquot_submitter_id"])
        for row in rows["PDC000204"]
        if row["aliquot_submitter_id"] != "ref"
    ]
    with pytest.raises(ValueError, match="disagrees"):
        capture._validate_matched_biospecimens(rows, labels)


def test_matched_biospecimens_expose_gbm_cohort_oracles() -> None:
    rows = _biospecimen_rows()
    labels = [
        str(row["aliquot_submitter_id"])
        for row in rows["PDC000204"]
        if row["aliquot_submitter_id"] != "ref"
    ]
    oracles = capture._validate_matched_biospecimens(rows, labels)
    assert oracles == {
        "official_rows_per_study": {"PDC000204": 111, "PDC000205": 111},
        "matched_non_pool_aliquots": 110,
        "shared_primary_tumors": 100,
        "shared_solid_tissue_normals": 10,
        "shared_qualified_cases": 109,
        "shared_disqualified_cases": 1,
        "pool_label": "ref",
    }


def test_capture_reverifies_and_writes_only_beside_private_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / capture.SAMPLE_MAP_FILES["PDC000204"]).write_bytes(_sample_map("P"))
    (source / capture.SAMPLE_MAP_FILES["PDC000205"]).write_bytes(_sample_map("P"))
    destination = source / capture.MANIFEST_FILENAME
    verify_calls: list[Path] = []

    def verify(root: Path) -> dict[str, Path]:
        verify_calls.append(root)
        return {name: root / name for name in capture.SAMPLE_MAP_FILES.values()}

    monkeypatch.setattr(capture, "verify_local_files", verify)
    bios = _biospecimen_rows()
    file_rows = {
        study: [
            {
                "file_name": lock.filename,
                "file_id": lock.file_uuid,
                "file_size": lock.bytes,
                "md5sum": lock.md5,
                "data_category": "Protein Assembly",
            }
            for lock in capture.SOURCE_FILES
            if lock.study_id == study
        ]
        for study in capture.STUDY_VERSIONS
    }

    def post(query: str) -> dict[str, object]:
        for study, value in capture.STUDY_QUERY.items():
            if query == value:
                return {"study": [{"study_id": capture.STUDY_VERSIONS[study]}]}
        for study, value in capture.FILE_QUERY.items():
            if query == value:
                return {"filesPerStudy": file_rows[study]}
        for study, value in capture.BIOSPECIMEN_QUERY.items():
            if query == value:
                return {"biospecimenPerStudy": bios[study]}
        raise AssertionError

    monkeypatch.setattr(capture, "_post", post)
    manifest = capture.capture(source, destination)
    assert verify_calls == [source.resolve(), source.resolve()]
    assert destination.read_bytes() == capture._canonical_bytes(manifest)
    parsed = cast("dict[str, object]", json.loads(destination.read_bytes()))
    assert parsed["schema_version"] == capture.MANIFEST_SCHEMA


def test_destination_must_be_private_source_sibling(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    with pytest.raises(ValueError, match="beside its inputs"):
        capture._validate_destination(source, tmp_path / "manifest.json")
