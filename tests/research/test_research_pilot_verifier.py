from __future__ import annotations

import hashlib
import zipfile
from typing import TYPE_CHECKING

import pytest
from tools.verify_research_pilot import (
    MAX_EVIDENCE_BYTES,
    ResearchPilotEvidenceError,
    _artifact_receipt,
    _ArtifactReceipt,
    _read,
    _verify_external_artifact,
)

if TYPE_CHECKING:
    from pathlib import Path


def _wheel_receipt(tmp_path: Path) -> _ArtifactReceipt:
    path = tmp_path / "pilot.whl"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("glio_proteogen/__init__.py", "")
    payload = path.read_bytes()
    return _ArtifactReceipt(
        kind="wheel",
        filename=path.name,
        size=len(payload),
        digest=hashlib.sha256(payload).hexdigest(),
        members=1,
    )


def test_verifier_binds_archive_bytes_and_member_count(tmp_path: Path) -> None:
    receipt = _wheel_receipt(tmp_path)
    _verify_external_artifact(tmp_path, receipt)
    (tmp_path / receipt.filename).write_bytes(b"tampered")
    with pytest.raises(ResearchPilotEvidenceError, match="bytes"):
        _verify_external_artifact(tmp_path, receipt)


def test_verifier_rejects_unsafe_receipt_and_oversized_evidence(tmp_path: Path) -> None:
    with pytest.raises(ResearchPilotEvidenceError, match="unsafe"):
        _artifact_receipt(
            {
                "kind": "wheel",
                "filename": "../outside.whl",
                "bytes": 1,
                "sha256": "0" * 64,
                "members": 1,
            }
        )
    evidence = tmp_path / "oversized.json"
    evidence.write_bytes(b"{" + b" " * MAX_EVIDENCE_BYTES + b"}")
    with pytest.raises(ResearchPilotEvidenceError, match="bounded size"):
        _read(tmp_path, evidence.name)
