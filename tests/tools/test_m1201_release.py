from __future__ import annotations

import json
from pathlib import Path

import pytest
from tools.verify_m1201_release import verify_release

_ROOT = Path(__file__).parents[2]
_EVIDENCE = _ROOT / "release-evidence" / "m12_01"


def test_m1201_release_evidence_is_fixture_budget_coverage_and_package_bound() -> None:
    report = verify_release(_EVIDENCE)
    assert report["module_id"] == "GLIO-PROTEOGEN-M12-01"
    assert report["evaluation"] == "passed"
    assert report["benchmark"] == "passed"
    assert report["package"] == "passed"


@pytest.mark.parametrize("field", ["cases", "fixture_sha256"])
def test_m1201_release_rejects_tampered_evaluator_identity(tmp_path: Path, field: str) -> None:
    for source in _EVIDENCE.iterdir():
        (tmp_path / source.name).write_bytes(source.read_bytes())
    evaluation_path = tmp_path / "evaluation.json"
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    if field == "cases":
        evaluation[field] = [
            {"case_id": "attacker", "expected": "supported", "actual": "supported"}
        ]
    else:
        evaluation[field] = "sha256:" + "0" * 64
    evaluation_path.write_text(json.dumps(evaluation), encoding="utf-8")
    with pytest.raises(ValueError, match="release evidence"):
        verify_release(tmp_path)


def test_m1201_release_rejects_package_hash_or_import_tampering(tmp_path: Path) -> None:
    for source in _EVIDENCE.iterdir():
        (tmp_path / source.name).write_bytes(source.read_bytes())
    package_path = tmp_path / "package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    package["wheel"]["sha256"] = "bad"
    package_path.write_text(json.dumps(package), encoding="utf-8")
    with pytest.raises(ValueError, match="release evidence"):
        verify_release(tmp_path)
