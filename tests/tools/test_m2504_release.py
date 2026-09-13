"""Independent release-evidence checks for M25-04."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from tools import verify_m2504_release as verifier


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_package_receipt(root: Path, wheel: Path, sdist: Path, *, members: int = 2) -> None:
    evidence = root / "release-evidence" / "m25_04"
    package = {
        "module_id": verifier.MODULE,
        "passed": True,
        "isolated_import": True,
        "wheel": {
            "filename": wheel.name,
            "member_count": members,
            "sha256": _sha256(wheel),
            "size_bytes": wheel.stat().st_size,
        },
        "sdist": {
            "filename": sdist.name,
            "sha256": _sha256(sdist),
            "size_bytes": sdist.stat().st_size,
        },
    }
    (evidence / "package.json").write_text(json.dumps(package), encoding="utf-8")


def _fixture_release(tmp_path: Path) -> tuple[Path, Path, Path]:
    source = Path(__file__).parents[2] / "release-evidence" / "m25_04"
    evidence = tmp_path / "release-evidence" / "m25_04"
    evidence.mkdir(parents=True)
    for filename in ("evaluation.json", "benchmark.json", "coverage.json"):
        (evidence / filename).write_bytes((source / filename).read_bytes())

    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    wheel = artifacts / "m2504-fixture.whl"
    with ZipFile(wheel, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("glio_proteogen/__init__.py", "")
        archive.writestr("glio_proteogen/py.typed", "")
    sdist = artifacts / "m2504-fixture.tar.gz"
    sdist.write_bytes(b"synthetic M25-04 source distribution")
    _write_package_receipt(tmp_path, wheel, sdist)
    return tmp_path, wheel, sdist


@pytest.mark.historical_artifact
def test_m2504_release_evidence_is_internally_consistent() -> None:
    root = Path(__file__).parents[2]
    wheel = root / "dist-m25-04" / "glio_proteogen-0.1.0-py3-none-any.whl"
    sdist = root / "dist-m25-04" / "glio_proteogen-0.1.0.tar.gz"
    report = verifier.verify(root, wheel, sdist)
    assert report["passed"] is True
    checks = report["checks"]
    assert isinstance(checks, dict)
    assert all(value is True for value in checks.values())


def test_m2504_release_verifier_accepts_self_contained_receipts_and_artifacts(
    tmp_path: Path,
) -> None:
    root, wheel, sdist = _fixture_release(tmp_path)

    report = verifier.verify(root, wheel, sdist)

    assert report == {
        "module_id": verifier.MODULE,
        "checks": {
            "module": True,
            "authority": True,
            "dependency": True,
            "evaluation": True,
            "benchmark": True,
            "coverage": True,
            "package": True,
            "wheel_members": True,
        },
        "passed": True,
    }


@pytest.mark.parametrize(
    ("filename", "field", "replacement", "failed_check"),
    [
        ("evaluation.json", "module_id", "GLIO-PROTEOGEN-M25-XX", "module"),
        ("evaluation.json", "dossier_slice", "forged", "authority"),
        ("evaluation.json", "upstream_dependency", "M25-02 only", "dependency"),
        ("evaluation.json", "adversarial_case_count", 11, "evaluation"),
        ("benchmark.json", "mean_ns", verifier.MEAN_BUDGET_NS + 1, "benchmark"),
        ("coverage.json", "coverage_percent", verifier.MIN_COVERAGE - 0.1, "coverage"),
    ],
)
def test_m2504_release_verifier_fails_closed_on_evidence_tamper(
    tmp_path: Path,
    filename: str,
    field: str,
    replacement: object,
    failed_check: str,
) -> None:
    root, _, _ = _fixture_release(tmp_path)
    path = root / "release-evidence" / "m25_04" / filename
    receipt = json.loads(path.read_text(encoding="utf-8"))
    receipt[field] = replacement
    path.write_text(json.dumps(receipt), encoding="utf-8")

    report = verifier.verify(root)

    assert report["passed"] is False
    checks = report["checks"]
    assert isinstance(checks, dict)
    assert checks[failed_check] is False


def test_m2504_release_verifier_binds_package_bytes(tmp_path: Path) -> None:
    root, wheel, sdist = _fixture_release(tmp_path)
    sdist.write_bytes(sdist.read_bytes() + b"tampered")

    report = verifier.verify(root, wheel, sdist)

    assert report["passed"] is False
    checks = report["checks"]
    assert isinstance(checks, dict)
    assert checks["package"] is False
    assert "wheel_members" not in checks


def test_m2504_release_verifier_rejects_digest_valid_non_zip_wheel(tmp_path: Path) -> None:
    root, wheel, sdist = _fixture_release(tmp_path)
    wheel.write_bytes(b"not a zip archive")
    _write_package_receipt(root, wheel, sdist, members=1)

    report = verifier.verify(root, wheel, sdist)

    assert report["passed"] is False
    checks = report["checks"]
    assert isinstance(checks, dict)
    assert checks["package"] is True
    assert checks["wheel_members"] is False


def test_m2504_release_verifier_rejects_malformed_package_record(tmp_path: Path) -> None:
    root, wheel, sdist = _fixture_release(tmp_path)
    package_path = root / "release-evidence" / "m25_04" / "package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    package["sdist"] = ["forged"]
    package_path.write_text(json.dumps(package), encoding="utf-8")

    report = verifier.verify(root, wheel, sdist)

    assert report["passed"] is False
    checks = report["checks"]
    assert isinstance(checks, dict)
    assert checks["package"] is False


def test_m2504_release_verifier_rejects_non_object_receipt(tmp_path: Path) -> None:
    root, _, _ = _fixture_release(tmp_path)
    (root / "release-evidence" / "m25_04" / "coverage.json").write_text("[]", encoding="utf-8")

    with pytest.raises(TypeError, match="must contain a JSON object"):
        verifier.verify(root)


def test_m2504_release_verifier_cli_reports_success_and_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, wheel, sdist = _fixture_release(tmp_path)
    argv = ["--root", str(root), "--wheel", str(wheel), "--sdist", str(sdist)]
    assert verifier.main(argv) == 0
    assert json.loads(capsys.readouterr().out)["passed"] is True

    sdist.write_bytes(b"tampered")
    assert verifier.main(argv) == 1
    assert json.loads(capsys.readouterr().out)["passed"] is False
