"""Adversarial tests for M10-03 release evidence verification."""

import json
import shutil
from pathlib import Path

import pytest
from tools.verify_m1003_release import M1003ReleaseVerificationError, verify_release


def _copy_release_tree(tmp_path: Path) -> Path:
    root = tmp_path / "release"
    shutil.copytree("release-evidence", root / "release-evidence")
    shutil.copytree("dist-m10-03", root / "dist-m10-03")
    shutil.copytree("tests/fixtures/m10_03", root / "tests/fixtures/m10_03")
    return root


def test_release_verifier_accepts_complete_receipt() -> None:
    result = verify_release()
    assert result == {"module": "GLIO-PROTEOGEN-M10-03", "verified": True}


def test_release_verifier_rejects_fixture_case_tampering(tmp_path: Path) -> None:
    root = _copy_release_tree(tmp_path)
    path = root / "release-evidence/M10-03/evaluation.json"
    evidence = json.loads(path.read_text(encoding="utf-8"))
    evidence["executed_cases"] = 10
    path.write_text(json.dumps(evidence), encoding="utf-8")
    with pytest.raises(M1003ReleaseVerificationError, match="evaluation did not pass"):
        verify_release(root)


def test_release_verifier_rejects_package_hash_tampering(tmp_path: Path) -> None:
    root = _copy_release_tree(tmp_path)
    path = root / "release-evidence/M10-03/package.json"
    evidence = json.loads(path.read_text(encoding="utf-8"))
    evidence["wheel"]["sha256"] = "0" * 64
    path.write_text(json.dumps(evidence), encoding="utf-8")
    with pytest.raises(M1003ReleaseVerificationError, match="digest mismatch"):
        verify_release(root)
