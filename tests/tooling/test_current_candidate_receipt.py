"""Strict generation and verification tests for the current-candidate receipt."""

from __future__ import annotations

import io
import json
import shutil
import tarfile
from hashlib import sha256
from typing import TYPE_CHECKING
from zipfile import ZipFile

import pytest
import tools.current_candidate_receipt as candidate_receipts
from tools.current_candidate_receipt import (
    RECEIPT_SCHEMA,
    CandidateReceiptError,
    build_receipt,
    verify_receipt,
    write_receipt,
)

if TYPE_CHECKING:
    from pathlib import Path

COMMIT = "1" * 40
PROFILE: dict[str, object] = {
    "algorithm_id": "glio-ecgi",
    "algorithm_version": "1.0.0",
    "demo_graph_digest": "sha256:" + "2" * 64,
    "numpy_version": "2.5.2",
    "profile_digest": "sha256:" + "3" * 64,
    "profile_id": "glio-ecgi/1.0.0",
}
RESEARCH_MEMBERS = (
    "glio_proteogen/research/cohort.py",
    "glio_proteogen/research/cohort_provenance.py",
    "glio_proteogen/research/pdc.py",
    "glio_proteogen/research/pipeline.py",
    "glio_proteogen/research/protein.py",
    "glio_proteogen/research/public_proteomics/pdc.py",
    "glio_proteogen/research/public_proteomics/provenance.py",
    "glio_proteogen/research/search.py",
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _write_wheel(path: Path, *, duplicate: bool = False) -> None:
    metadata = "Metadata-Version: 2.4\nName: glio-proteogen\nVersion: 0.1.0\n"
    with ZipFile(path, "w") as archive:
        archive.writestr("glio_proteogen/__init__.py", '__version__ = "0.1.0"\n')
        archive.writestr("glio_proteogen-0.1.0.dist-info/METADATA", metadata)
        for member in RESEARCH_MEMBERS:
            archive.writestr(member, "")
        if duplicate:
            archive.writestr("glio_proteogen/__init__.py", "duplicate\n")


def _write_sdist(path: Path, *, unsafe: bool = False) -> None:
    members = {
        "glio_proteogen-0.1.0/PKG-INFO": (
            b"Metadata-Version: 2.4\nName: glio-proteogen\nVersion: 0.1.0\n"
        ),
        "glio_proteogen-0.1.0/src/glio_proteogen/__init__.py": (
            b'__version__ = "0.1.0"\n'
        ),
    }
    for member in RESEARCH_MEMBERS:
        members[f"glio_proteogen-0.1.0/src/{member}"] = b""
    if unsafe:
        members["../escaped"] = b"unsafe"
    with tarfile.open(path, "w:gz") as archive:
        for name, payload in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))


def _artifacts(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    first = tmp_path / "one"
    second = tmp_path / "two"
    first.mkdir()
    second.mkdir()
    wheel = first / "glio_proteogen-0.1.0-py3-none-any.whl"
    sdist = first / "glio_proteogen-0.1.0.tar.gz"
    replay_wheel = second / wheel.name
    replay_sdist = second / sdist.name
    _write_wheel(wheel)
    _write_sdist(sdist)
    shutil.copyfile(wheel, replay_wheel)
    shutil.copyfile(sdist, replay_sdist)
    return wheel, sdist, replay_wheel, replay_sdist


def _receipt_file(
    tmp_path: Path,
    wheel: Path,
    sdist: Path,
    replay_wheel: Path,
    replay_sdist: Path,
) -> Path:
    receipt = build_receipt(
        wheel,
        sdist,
        replay_wheel,
        replay_sdist,
        source_commit=COMMIT,
        profile=PROFILE,
    )
    path = tmp_path / "current-candidate.json"
    write_receipt(path, receipt)
    return path


def _write_forged_receipt(path: Path, payload: dict[str, object]) -> None:
    payload.pop("receipt_digest", None)
    payload["receipt_digest"] = "sha256:" + sha256(_canonical(payload)).hexdigest()
    path.write_bytes(_canonical(payload))


def test_current_candidate_receipt_is_deterministic_and_artifact_bound(tmp_path: Path) -> None:
    wheel, sdist, replay_wheel, replay_sdist = _artifacts(tmp_path)
    first = build_receipt(
        wheel,
        sdist,
        replay_wheel,
        replay_sdist,
        source_commit=COMMIT,
        profile=PROFILE,
    )
    second = build_receipt(
        wheel,
        sdist,
        replay_wheel,
        replay_sdist,
        source_commit=COMMIT,
        profile=PROFILE,
    )
    assert first == second
    assert first["receipt_schema"] == RECEIPT_SCHEMA
    output = tmp_path / "receipt.json"
    write_receipt(output, first)
    assert output.read_bytes() == _canonical(first) + b"\n"

    verified = verify_receipt(
        output,
        wheel,
        sdist,
        replay_wheel=replay_wheel,
        replay_sdist=replay_sdist,
        expected_source_commit=COMMIT,
        expected_profile=PROFILE,
    )
    artifacts = verified["artifacts"]
    assert isinstance(artifacts, dict)
    for label in ("wheel", "sdist"):
        record = artifacts[label]
        assert isinstance(record, dict)
        inventory = record["member_inventory"]
        assert isinstance(inventory, dict)
        assert inventory["count"] == len(inventory["members"])


def test_current_candidate_receipt_rejects_nonidentical_second_build(tmp_path: Path) -> None:
    wheel, sdist, replay_wheel, replay_sdist = _artifacts(tmp_path)
    replay_wheel.write_bytes(replay_wheel.read_bytes() + b"tamper")
    with pytest.raises(CandidateReceiptError, match="byte-identical"):
        build_receipt(
            wheel,
            sdist,
            replay_wheel,
            replay_sdist,
            source_commit=COMMIT,
            profile=PROFILE,
        )


def test_current_candidate_receipt_rejects_changed_artifact_and_commit(tmp_path: Path) -> None:
    wheel, sdist, replay_wheel, replay_sdist = _artifacts(tmp_path)
    receipt = _receipt_file(tmp_path, wheel, sdist, replay_wheel, replay_sdist)
    with pytest.raises(CandidateReceiptError, match="source commit"):
        verify_receipt(
            receipt,
            wheel,
            sdist,
            expected_source_commit="4" * 40,
            expected_profile=PROFILE,
        )
    wheel.write_bytes(wheel.read_bytes() + b"tamper")
    with pytest.raises(CandidateReceiptError, match="wheel does not match"):
        verify_receipt(
            receipt,
            wheel,
            sdist,
            expected_source_commit=COMMIT,
            expected_profile=PROFILE,
        )


def test_current_candidate_receipt_rejects_forged_profile_and_source_epoch(
    tmp_path: Path,
) -> None:
    wheel, sdist, replay_wheel, replay_sdist = _artifacts(tmp_path)
    receipt = _receipt_file(tmp_path, wheel, sdist, replay_wheel, replay_sdist)
    original = json.loads(receipt.read_text(encoding="utf-8"))

    profile_payload = json.loads(json.dumps(original))
    profile_payload["profile"]["profile_id"] = "glio-ecgi/forged"
    forged_profile = tmp_path / "forged-profile.json"
    _write_forged_receipt(forged_profile, profile_payload)
    with pytest.raises(CandidateReceiptError, match="profile does not match runtime"):
        verify_receipt(
            forged_profile,
            wheel,
            sdist,
            expected_source_commit=COMMIT,
            expected_profile=PROFILE,
        )

    epoch_payload = json.loads(json.dumps(original))
    epoch_payload["reproducibility"]["source_date_epoch"] += 1
    forged_epoch = tmp_path / "forged-epoch.json"
    _write_forged_receipt(forged_epoch, epoch_payload)
    with pytest.raises(CandidateReceiptError, match="reproducibility policy"):
        verify_receipt(
            forged_epoch,
            wheel,
            sdist,
            expected_source_commit=COMMIT,
            expected_profile=PROFILE,
        )


def test_current_candidate_receipt_rejects_forged_inventory_with_valid_self_digest(
    tmp_path: Path,
) -> None:
    wheel, sdist, replay_wheel, replay_sdist = _artifacts(tmp_path)
    receipt_path = _receipt_file(tmp_path, wheel, sdist, replay_wheel, replay_sdist)
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload["artifacts"]["wheel"]["member_inventory"]["members"].pop()
    payload["artifacts"]["wheel"]["member_inventory"]["count"] -= 1
    payload["artifacts"]["wheel"]["members"] -= 1
    members = payload["artifacts"]["wheel"]["member_inventory"]["members"]
    payload["artifacts"]["wheel"]["member_inventory"]["sha256"] = sha256(
        _canonical(sorted(members))
    ).hexdigest()
    forged = tmp_path / "forged.json"
    _write_forged_receipt(forged, payload)

    with pytest.raises(CandidateReceiptError, match="wheel does not match"):
        verify_receipt(
            forged,
            wheel,
            sdist,
            expected_source_commit=COMMIT,
            expected_profile=PROFILE,
        )


def test_current_candidate_receipt_rejects_duplicate_json_and_archive_members(
    tmp_path: Path,
) -> None:
    duplicate_json = tmp_path / "duplicate.json"
    duplicate_json.write_text('{"receipt_schema":"a","receipt_schema":"b"}', encoding="utf-8")
    wheel, sdist, replay_wheel, replay_sdist = _artifacts(tmp_path)
    with pytest.raises(CandidateReceiptError, match="duplicate key"):
        verify_receipt(
            duplicate_json,
            wheel,
            sdist,
            expected_profile=PROFILE,
        )

    with pytest.warns(UserWarning, match="Duplicate name"):
        _write_wheel(wheel, duplicate=True)
    shutil.copyfile(wheel, replay_wheel)
    with pytest.raises(CandidateReceiptError, match="duplicate members"):
        build_receipt(
            wheel,
            sdist,
            replay_wheel,
            replay_sdist,
            source_commit=COMMIT,
            profile=PROFILE,
        )


def test_current_candidate_receipt_rejects_unsafe_archive_and_overwrite(
    tmp_path: Path,
) -> None:
    wheel, sdist, replay_wheel, replay_sdist = _artifacts(tmp_path)
    receipt = build_receipt(
        wheel,
        sdist,
        replay_wheel,
        replay_sdist,
        source_commit=COMMIT,
        profile=PROFILE,
    )
    output = tmp_path / "receipt.json"
    write_receipt(output, receipt)
    with pytest.raises(CandidateReceiptError, match="already exists"):
        write_receipt(output, receipt)

    _write_sdist(sdist, unsafe=True)
    shutil.copyfile(sdist, replay_sdist)
    with pytest.raises(CandidateReceiptError, match="unsafe member"):
        build_receipt(
            wheel,
            sdist,
            replay_wheel,
            replay_sdist,
            source_commit=COMMIT,
            profile=PROFILE,
        )


def test_current_candidate_receipt_cli_generates_verifies_and_refuses_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    wheel, sdist, replay_wheel, replay_sdist = _artifacts(tmp_path)
    receipt = tmp_path / "cli-receipt.json"
    monkeypatch.setattr(candidate_receipts, "_profile_identity", lambda: PROFILE)
    artifact_arguments = [
        "--wheel",
        str(wheel),
        "--sdist",
        str(sdist),
        "--replay-wheel",
        str(replay_wheel),
        "--replay-sdist",
        str(replay_sdist),
        "--source-commit",
        COMMIT,
    ]

    generate_arguments = ["generate", *artifact_arguments, "--output", str(receipt)]
    assert candidate_receipts.main(generate_arguments) == 0
    assert candidate_receipts.main(["verify", *artifact_arguments, str(receipt)]) == 0
    assert candidate_receipts.main(generate_arguments) == 1
    captured = capsys.readouterr()
    assert "current candidate receipt verify passed" in captured.out
    assert "output already exists" in captured.err
