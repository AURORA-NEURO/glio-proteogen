"""Adversarial checks for public-proteomics package receipts."""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
from typing import TYPE_CHECKING
from zipfile import ZipFile

import pytest
from tools.verify_research_public_proteomics import (
    VerificationError,
    _member_inventory_digest,
    _verify_member_inventory,
    _verify_package,
    _verify_reproducibility,
)

if TYPE_CHECKING:
    from pathlib import Path


def _wheel(tmp_path: Path, names: tuple[str, ...]) -> Path:
    path = tmp_path / "fixture.whl"
    with ZipFile(path, "w") as archive:
        for name in names:
            archive.writestr(name, name.encode())
    return path


def _sdist(tmp_path: Path, names: tuple[str, ...]) -> Path:
    path = tmp_path / "fixture.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        for name in names:
            payload = name.encode()
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return path


def _receipt(path: Path, names: list[str]) -> dict[str, object]:
    return {
        "filename": path.name,
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "members": len(names),
        "member_inventory": {
            "count": len(names),
            "sha256": _member_inventory_digest(names),
            "members": sorted(names),
        },
    }


def test_public_package_verifier_binds_full_wheel_inventory(tmp_path: Path) -> None:
    names = (
        "glio_proteogen/research/public_proteomics/pdc.py",
        "glio_proteogen/research/public_proteomics/__init__.py",
    )
    artifact = _wheel(tmp_path, names)
    record = _receipt(artifact, list(names))
    _verify_package(artifact, {"wheel": record})

    forged = json.loads(json.dumps(record))
    forged["member_inventory"]["members"] = [names[0]]
    with pytest.raises(VerificationError, match="member inventory"):
        _verify_package(artifact, {"wheel": forged})


def test_public_package_verifier_binds_full_sdist_inventory(tmp_path: Path) -> None:
    names = (
        "fixture/src/glio_proteogen/research/public_proteomics/pdc.py",
        "fixture/src/glio_proteogen/research/public_proteomics/__init__.py",
    )
    artifact = _sdist(tmp_path, names)
    record = _receipt(artifact, list(names))
    _verify_package(artifact, {"sdist": record})

    forged = json.loads(json.dumps(record))
    forged["member_inventory"]["sha256"] = "0" * 64
    with pytest.raises(VerificationError, match="member inventory"):
        _verify_package(artifact, {"sdist": forged})


def test_public_package_verifier_rejects_duplicate_archive_members() -> None:
    names = (
        "glio_proteogen/research/public_proteomics/pdc.py",
        "glio_proteogen/research/public_proteomics/pdc.py",
    )
    with pytest.raises(VerificationError, match="duplicate"):
        _verify_member_inventory({"member_inventory": {}}, list(names))


def test_public_package_verifier_requires_reproducible_receipts() -> None:
    valid = {
        "reproducible_two_builds": True,
        "source_date_epoch": 315532800,
        "reproducible_hashes": {"wheel": "a" * 64, "sdist": "b" * 64},
        "wheel": {"sha256": "a" * 64},
        "sdist": {"sha256": "b" * 64},
    }
    _verify_reproducibility(valid)

    forged = json.loads(json.dumps(valid))
    forged["source_date_epoch"] = 0
    with pytest.raises(VerificationError, match="SOURCE_DATE_EPOCH"):
        _verify_reproducibility(forged)
