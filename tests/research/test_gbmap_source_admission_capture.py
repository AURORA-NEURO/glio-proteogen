"""Focused safety and determinism checks for the local GBmap fingerprint tool."""

from __future__ import annotations

import hashlib
import json
import os
from typing import TYPE_CHECKING, cast

import pytest

from glio_proteogen.research.gbmap_deconvolution.errors import GbmapSourceAdmissionError
from glio_proteogen.research.gbmap_deconvolution.extraction import (
    ZENODO_SOURCE_ID,
    SourceFingerprint,
)
from tools import capture_gbmap_source_admission as capture

if TYPE_CHECKING:
    from pathlib import Path


def _fixture(tmp_path: Path) -> tuple[Path, int, str, str]:
    source = tmp_path / "private" / "fixture.h5ad"
    source.parent.mkdir()
    content = b"bounded-gbmap-h5ad-fixture\x00\x01\x02"
    source.write_bytes(content)
    md5 = hashlib.md5(content, usedforsecurity=False).hexdigest()
    sha256 = f"sha256:{hashlib.sha256(content).hexdigest()}"
    return source, len(content), md5, sha256


def _capture(
    source: Path,
    expected_bytes: int,
    expected_md5: str,
    repository_root: Path,
    reviewed_sha256: str | None = None,
) -> capture._GbmapTestFixtureReceipt:
    return capture._capture_test_fixture_receipt(
        source,
        expected_bytes=expected_bytes,
        expected_md5=expected_md5,
        repository_root=repository_root,
        reviewed_sha256=reviewed_sha256,
    )


def _repository(tmp_path: Path) -> Path:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    return repository_root


def test_good_fixture_emits_canonical_test_only_non_admission_receipt(tmp_path: Path) -> None:
    source, size, md5, sha256 = _fixture(tmp_path)
    receipt = _capture(source, size, md5, _repository(tmp_path), sha256)
    payload = capture.canonical_receipt_bytes(receipt)
    parsed = cast("dict[str, object]", json.loads(payload))

    assert payload.endswith(b"\n")
    assert payload == capture.canonical_receipt_bytes(receipt)
    assert parsed["schema_version"] != capture.RECEIPT_SCHEMA
    assert parsed["source_id"] != ZENODO_SOURCE_ID
    assert parsed["artifact_name"] != capture.PRODUCTION_ARTIFACT_NAME
    assert parsed["source_sha256"] == sha256
    assert parsed["review_match"] is True
    assert parsed["admission_state"] == "review_digest_matches_not_admitted"
    assert parsed["admission_granted"] is False


@pytest.mark.parametrize("field", ["bytes", "md5"])
def test_wrong_source_lock_fails_without_a_receipt(tmp_path: Path, field: str) -> None:
    source, size, md5, _sha256 = _fixture(tmp_path)
    if field == "bytes":
        size += 1
        match = "length"
    else:
        md5 = "0" * 32
        match = "MD5"

    with pytest.raises(GbmapSourceAdmissionError, match=match):
        _capture(source, size, md5, _repository(tmp_path))


def test_reviewed_digest_mismatch_is_explicit_and_never_admits(tmp_path: Path) -> None:
    source, size, md5, _sha256 = _fixture(tmp_path)

    receipt = _capture(
        source,
        size,
        md5,
        _repository(tmp_path),
        f"sha256:{'f' * 64}",
    )

    assert not receipt.review_match
    assert receipt.admission_state == "review_digest_mismatch_not_admitted"
    assert not receipt.admission_granted


def test_receipt_excludes_source_path_raw_content_and_identifiers(tmp_path: Path) -> None:
    source = tmp_path / "private" / "PW032-701_R4-nc_cell-barcode.h5ad"
    source.parent.mkdir()
    content = b"PW032-701 R4 n.c. AAAC-cell-barcode"
    source.write_bytes(content)
    payload = capture.canonical_receipt_bytes(
        _capture(
            source,
            len(content),
            hashlib.md5(content, usedforsecurity=False).hexdigest(),
            _repository(tmp_path),
        )
    ).decode("utf-8")

    assert str(source) not in payload
    for forbidden in ("PW032-701", "R4 n.c.", "AAAC-cell-barcode"):
        assert forbidden not in payload
    parsed = cast("dict[str, object]", json.loads(payload))
    assert parsed["source_path_retained"] is False
    assert parsed["cell_level_material_retained"] is False
    assert parsed["donor_identifiers_retained"] is False
    assert parsed["raw_content_retained"] is False


def test_production_capture_rejects_expectation_and_repository_overrides(tmp_path: Path) -> None:
    source, size, md5, _sha256 = _fixture(tmp_path)
    repository_root = _repository(tmp_path)

    with pytest.raises(TypeError, match="unexpected keyword argument"):
        capture.capture_source_receipt(  # type: ignore[call-arg]
            source,
            expectation=capture._SourceExpectation(size, md5),
        )
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        capture.capture_source_receipt(  # type: ignore[call-arg]
            source,
            repository_root=repository_root,
        )


def test_fixture_hook_cannot_accept_production_identity_or_schema(tmp_path: Path) -> None:
    source, size, md5, _sha256 = _fixture(tmp_path)

    with pytest.raises(TypeError, match="unexpected keyword argument"):
        capture._capture_test_fixture_receipt(  # type: ignore[call-arg]
            source,
            expected_bytes=size,
            expected_md5=md5,
            repository_root=_repository(tmp_path),
            source_id=ZENODO_SOURCE_ID,
            schema_version=capture.RECEIPT_SCHEMA,
        )


def test_source_inside_repository_is_rejected_before_hashing(tmp_path: Path) -> None:
    repository_root = _repository(tmp_path)
    source = repository_root / "fixture.h5ad"
    content = b"fixture"
    source.write_bytes(content)

    with pytest.raises(GbmapSourceAdmissionError, match="outside the repository"):
        _capture(
            source,
            len(content),
            hashlib.md5(content, usedforsecurity=False).hexdigest(),
            repository_root,
        )


def test_path_bearing_fingerprint_failure_is_sanitized_without_exception_chain(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source, size, md5, _sha256 = _fixture(tmp_path)
    path_failure = GbmapSourceAdmissionError(str(source))
    path_failure.__cause__ = OSError(str(source))

    def fail_with_path(_source: Path) -> SourceFingerprint:
        raise path_failure

    monkeypatch.setattr(capture, "fingerprint_gbmap_source", fail_with_path)

    with pytest.raises(GbmapSourceAdmissionError) as captured:
        _capture(source, size, md5, _repository(tmp_path))

    assert str(source) not in str(captured.value)
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None


def test_receipt_is_fsynced_then_atomically_published_and_replay_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source, size, md5, sha256 = _fixture(tmp_path)
    repository_root = _repository(tmp_path)
    receipt = _capture(source, size, md5, repository_root, sha256)
    payload = capture.canonical_receipt_bytes(receipt)
    destination = tmp_path / "receipts" / "gbmap.json"
    real_fsync = os.fsync
    real_link = os.link
    events: list[str] = []

    def observed_fsync(descriptor: int) -> None:
        events.append("fsync")
        real_fsync(descriptor)

    def observed_link(temporary: Path, final: Path) -> None:
        assert temporary.parent == destination.parent
        assert temporary.name.startswith(capture._TEMP_PREFIX)
        assert temporary.name.endswith(capture._TEMP_SUFFIX)
        assert events == ["fsync"]
        events.append("link")
        real_link(temporary, final)

    monkeypatch.setattr(os, "fsync", observed_fsync)
    monkeypatch.setattr(os, "link", observed_link)

    capture.write_receipt(destination, payload, source=source)
    capture.write_receipt(destination, payload, source=source)

    assert events == ["fsync", "link"]
    assert destination.read_bytes() == payload
    assert not tuple(destination.parent.glob(f"{capture._TEMP_PREFIX}*{capture._TEMP_SUFFIX}"))


def test_output_cannot_replace_source_or_overwrite_different_receipt(tmp_path: Path) -> None:
    source, size, md5, _sha256 = _fixture(tmp_path)
    payload = capture.canonical_receipt_bytes(_capture(source, size, md5, _repository(tmp_path)))

    with pytest.raises(GbmapSourceAdmissionError, match="cannot replace"):
        capture.write_receipt(source, payload, source=source)

    destination = tmp_path / "receipt.json"
    destination.write_text("different", encoding="utf-8")
    with pytest.raises(GbmapSourceAdmissionError, match="refusing to overwrite"):
        capture.write_receipt(destination, payload, source=source)
    assert not tuple(tmp_path.glob(f"{capture._TEMP_PREFIX}*{capture._TEMP_SUFFIX}"))


def test_failed_atomic_publication_is_sanitized_and_cleans_temporary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source, size, md5, _sha256 = _fixture(tmp_path)
    payload = capture.canonical_receipt_bytes(_capture(source, size, md5, _repository(tmp_path)))
    destination = tmp_path / "receipts" / "gbmap.json"

    def fail_link(_temporary: Path, _destination: Path) -> None:
        raise OSError(str(destination))

    monkeypatch.setattr(os, "link", fail_link)

    with pytest.raises(GbmapSourceAdmissionError) as captured:
        capture.write_receipt(destination, payload, source=source)

    assert str(destination) not in str(captured.value)
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert not destination.exists()
    assert not tuple(destination.parent.glob(f"{capture._TEMP_PREFIX}*{capture._TEMP_SUFFIX}"))


def test_failed_fsync_is_sanitized_and_cleans_temporary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source, size, md5, _sha256 = _fixture(tmp_path)
    payload = capture.canonical_receipt_bytes(_capture(source, size, md5, _repository(tmp_path)))
    destination = tmp_path / "receipts" / "gbmap.json"

    def fail_fsync(_descriptor: int) -> None:
        raise OSError(str(destination))

    monkeypatch.setattr(os, "fsync", fail_fsync)

    with pytest.raises(GbmapSourceAdmissionError) as captured:
        capture.write_receipt(destination, payload, source=source)

    assert str(destination) not in str(captured.value)
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert not destination.exists()
    assert not tuple(destination.parent.glob(f"{capture._TEMP_PREFIX}*{capture._TEMP_SUFFIX}"))


def test_interrupted_atomic_publication_cleans_temporary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source, size, md5, _sha256 = _fixture(tmp_path)
    payload = capture.canonical_receipt_bytes(_capture(source, size, md5, _repository(tmp_path)))
    destination = tmp_path / "receipts" / "gbmap.json"

    def interrupt_link(_temporary: Path, _destination: Path) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(os, "link", interrupt_link)

    with pytest.raises(KeyboardInterrupt):
        capture.write_receipt(destination, payload, source=source)

    assert not destination.exists()
    assert not tuple(destination.parent.glob(f"{capture._TEMP_PREFIX}*{capture._TEMP_SUFFIX}"))


def test_cli_stdout_and_optional_file_are_the_same_canonical_receipt(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    source, size, md5, sha256 = _fixture(tmp_path)
    repository_root = _repository(tmp_path)
    destination = tmp_path / "receipt.json"

    def fixture_capture(
        value: Path,
        *,
        reviewed_sha256: str | None = None,
    ) -> capture._GbmapTestFixtureReceipt:
        return _capture(value, size, md5, repository_root, reviewed_sha256)

    monkeypatch.setattr(capture, "capture_source_receipt", fixture_capture)

    exit_code = capture.main(
        [
            "--source",
            str(source),
            "--reviewed-sha256",
            sha256,
            "--output",
            str(destination),
        ]
    )
    streams = capsys.readouterr()

    assert exit_code == 0
    assert streams.err == ""
    assert streams.out.encode("utf-8") == destination.read_bytes()


def test_cli_review_mismatch_emits_evidence_and_returns_three(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    source, size, md5, _sha256 = _fixture(tmp_path)
    repository_root = _repository(tmp_path)

    def fixture_capture(
        value: Path,
        *,
        reviewed_sha256: str | None = None,
    ) -> capture._GbmapTestFixtureReceipt:
        return _capture(value, size, md5, repository_root, reviewed_sha256)

    monkeypatch.setattr(capture, "capture_source_receipt", fixture_capture)

    exit_code = capture.main(
        [
            "--source",
            str(source),
            "--reviewed-sha256",
            f"sha256:{'f' * 64}",
        ]
    )
    streams = capsys.readouterr()
    parsed = cast("dict[str, object]", json.loads(streams.out))

    assert exit_code == 3
    assert streams.err == ""
    assert parsed["review_match"] is False
    assert parsed["admission_granted"] is False
