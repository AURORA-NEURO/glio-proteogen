# ruff: noqa: T201, TRY003
"""Verify checksum-bound evidence for the additive public-proteomics foundation."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
from pathlib import Path
from zipfile import ZipFile

_ROOT = Path(__file__).resolve().parents[1]
_EVIDENCE = _ROOT / "docs" / "evidence" / "research_public_proteomics"
_FIXTURE = _ROOT / "research" / "fixtures" / "pdc" / "pdc000204.metadata.json"
_FIXTURE_MANIFEST = _ROOT / "research" / "fixtures" / "pdc" / "pdc000204.manifest.json"
_EXPECTED_SOURCE_DATE_EPOCH = 315532800
_REQUIRED_WHEEL_MEMBER = "glio_proteogen/research/public_proteomics/pdc.py"
_REQUIRED_SDIST_MEMBER = "src/glio_proteogen/research/public_proteomics/pdc.py"


class VerificationError(ValueError):
    """Raised when a release artifact disagrees with recorded evidence."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise VerificationError(f"{path} must contain a JSON object")
    return value


def _verify_fixture() -> None:
    manifest = _read_json(_FIXTURE_MANIFEST)
    fixture = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    canonical = json.dumps(
        fixture, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False
    ).encode("utf-8")
    observed = hashlib.sha256(canonical).hexdigest()
    expected = str(manifest["fixture_canonical_json_sha256"]).removeprefix("sha256:")
    if observed != expected or _FIXTURE.stat().st_size != manifest["fixture_file_bytes"]:
        raise VerificationError("PDC000204 fixture does not match its manifest")


def _member_inventory_digest(names: list[str]) -> str:
    canonical = json.dumps(
        sorted(names), ensure_ascii=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _verify_member_inventory(record: dict[str, object], names: list[str]) -> None:
    if len(names) != len(set(names)):
        raise VerificationError("package contains duplicate archive members")
    if any(not isinstance(name, str) or not name or "\x00" in name for name in names):
        raise VerificationError("package contains an invalid archive member name")
    inventory = record.get("member_inventory")
    if not isinstance(inventory, dict):
        raise VerificationError("package member inventory is missing")
    expected_names = inventory.get("members")
    observed_names = sorted(names)
    if expected_names != observed_names:
        raise VerificationError("package member inventory does not match archive")
    if inventory.get("count") != len(names) or record.get("members") != len(names):
        raise VerificationError("package member inventory count does not match archive")
    if inventory.get("sha256") != _member_inventory_digest(names):
        raise VerificationError("package member inventory digest does not match archive")


def _verify_package(path: Path, evidence: dict[str, object]) -> None:
    package_name = path.name
    if package_name.endswith(".whl"):
        record = evidence["wheel"]
        if not isinstance(record, dict):
            raise VerificationError("wheel evidence is malformed")
        with ZipFile(path) as archive:
            names = archive.namelist()
            if _REQUIRED_WHEEL_MEMBER not in names:
                raise VerificationError("wheel omits the PDC research client")
    elif package_name.endswith(".tar.gz"):
        record = evidence["sdist"]
        if not isinstance(record, dict):
            raise VerificationError("sdist evidence is malformed")
        with tarfile.open(path, "r:gz") as archive:
            sdist_names = archive.getnames()
            names = sdist_names
            if not any(name.endswith(_REQUIRED_SDIST_MEMBER) for name in names):
                raise VerificationError("sdist omits the PDC research client")
    else:
        raise VerificationError("artifact must be a wheel or sdist")
    if record.get("filename") != package_name or record.get("bytes") != path.stat().st_size:
        raise VerificationError(f"size/name evidence mismatch for {package_name}")
    if record.get("sha256") != _sha256(path):
        raise VerificationError(f"SHA-256 evidence mismatch for {package_name}")
    _verify_member_inventory(record, names)


def _verify_reproducibility(evidence: dict[str, object]) -> None:
    if evidence.get("reproducible_two_builds") is not True:
        raise VerificationError("package does not record two reproducible builds")
    if evidence.get("source_date_epoch") != _EXPECTED_SOURCE_DATE_EPOCH:
        raise VerificationError("package has an unexpected SOURCE_DATE_EPOCH")
    hashes = evidence.get("reproducible_hashes")
    wheel = evidence.get("wheel")
    sdist = evidence.get("sdist")
    if not isinstance(hashes, dict) or not isinstance(wheel, dict) or not isinstance(sdist, dict):
        raise VerificationError("package reproducibility receipts are malformed")
    if hashes.get("wheel") != wheel.get("sha256") or hashes.get("sdist") != sdist.get("sha256"):
        raise VerificationError("package reproducibility hashes do not match receipts")


def verify(wheel: Path, sdist: Path) -> None:
    """Verify the two final artifacts, fixture, and evidence records."""

    package = _read_json(_EVIDENCE / "package.json")
    _verify_fixture()
    _verify_reproducibility(package)
    _verify_package(wheel, package)
    _verify_package(sdist, package)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    parser.add_argument("sdist", type=Path)
    args = parser.parse_args()
    try:
        verify(args.wheel, args.sdist)
    except (OSError, KeyError, TypeError, ValueError, tarfile.TarError):
        print("research public-proteomics release verification failed", file=sys.stderr)
        return 1
    print("research public-proteomics release verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
