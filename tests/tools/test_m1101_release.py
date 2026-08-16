from __future__ import annotations

import json
from pathlib import Path

import pytest
from tools.verify_m1101_release import verify_release

_ROOT = Path(__file__).parents[2]
_EVIDENCE = _ROOT / "release-evidence" / "m11_01"


def test_m1101_release_evidence_is_fixture_and_budget_bound() -> None:
    report = verify_release(_EVIDENCE)
    assert report["module_id"] == "GLIO-PROTEOGEN-M11-01"
    assert report["evaluation"] == "passed"
    assert report["benchmark"] == "passed"


@pytest.mark.parametrize("field", ["case_ids", "fixture_digest"])
def test_m1101_release_rejects_tampered_evaluator_identity(tmp_path: Path, field: str) -> None:
    for source in _EVIDENCE.iterdir():
        (tmp_path / source.name).write_bytes(source.read_bytes())
    evaluation_path = tmp_path / "evaluation.json"
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    if field == "case_ids":
        evaluation[field] = ["attacker"]
    else:
        evaluation[field] = "sha256:" + "0" * 64
    evaluation_path.write_text(json.dumps(evaluation), encoding="utf-8")
    with pytest.raises(ValueError, match="release evidence"):
        verify_release(tmp_path)
