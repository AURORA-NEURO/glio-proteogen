"""Machine-readable M28-04 release evidence verification."""

import json
import shutil
from pathlib import Path

import pytest

from tools import verify_m2804_evidence

EXPECTED_CHECKS = 10


def test_m2804_release_evidence_is_cross_bound() -> None:
    report = verify_m2804_evidence.verify()
    assert report["module_id"] == "GLIO-PROTEOGEN-M28-04"
    assert report["evaluator_checks"] == EXPECTED_CHECKS
    assert report["generated_member_count"] == 0
    assert report["unsafe_path_count"] == 0
    assert report["passed"] is True


def test_m2804_release_evidence_rejects_tampered_package_hash(tmp_path: Path) -> None:
    evidence_root = verify_m2804_evidence.EVIDENCE_ROOT
    for path in evidence_root.glob("*.json"):
        shutil.copy2(path, tmp_path / path.name)
    package_path = tmp_path / "package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    package["wheel"]["sha256"] = "0" * 64
    package_path.write_text(json.dumps(package), encoding="utf-8")
    original_root = verify_m2804_evidence.EVIDENCE_ROOT
    verify_m2804_evidence.EVIDENCE_ROOT = tmp_path
    try:
        with pytest.raises(verify_m2804_evidence.M2804EvidenceError, match="wheel hash drifted"):
            verify_m2804_evidence.verify()
    finally:
        verify_m2804_evidence.EVIDENCE_ROOT = original_root
