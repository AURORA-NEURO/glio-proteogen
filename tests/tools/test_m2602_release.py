"""M26-02 release-evidence scenario-lock tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tools.verify_m26_02_release import M2602ReleaseError, _check_evaluation

_EVIDENCE = Path(__file__).parents[2] / "release-evidence" / "m26_02" / "evaluation.json"


def test_release_evidence_accepts_complete_replay_scenario_receipt() -> None:
    document = json.loads(_EVIDENCE.read_text(encoding="utf-8"))
    _check_evaluation(document)


def test_release_evidence_rejects_missing_semantic_replay_scenario() -> None:
    document = json.loads(_EVIDENCE.read_text(encoding="utf-8"))
    document["scenarioIds"] = document["scenarioIds"][:-1]
    with pytest.raises(M2602ReleaseError, match="scenario IDs"):
        _check_evaluation(document)
