"""Independent M24-07 release evidence verifier tests."""

from __future__ import annotations

import json
from pathlib import Path

from tools.verify_m2407_release import verify


def test_release_verifier_accepts_evidence_without_package(tmp_path: Path) -> None:
    evidence = tmp_path / "release-evidence" / "m24_07"
    evidence.mkdir(parents=True)
    source = Path(__file__).parents[2] / "release-evidence" / "m24_07"
    for name in ("evaluation.json", "benchmark.json", "coverage.json"):
        (evidence / name).write_bytes((source / name).read_bytes())
    report = verify(tmp_path)
    assert report["passed"] is True


def test_release_verifier_rejects_tampered_evaluation(tmp_path: Path) -> None:
    evidence = tmp_path / "release-evidence" / "m24_07"
    evidence.mkdir(parents=True)
    source = Path(__file__).parents[2] / "release-evidence" / "m24_07"
    for name in ("evaluation.json", "benchmark.json", "coverage.json"):
        payload = json.loads((source / name).read_text(encoding="utf-8"))
        if name == "evaluation.json":
            payload["scenario_count"] = 999
        (evidence / name).write_text(json.dumps(payload), encoding="utf-8")
    assert verify(tmp_path)["passed"] is False


def test_release_verifier_rejects_missing_semantic_replay_case(tmp_path: Path) -> None:
    evidence = tmp_path / "release-evidence" / "m24_07"
    evidence.mkdir(parents=True)
    source = Path(__file__).parents[2] / "release-evidence" / "m24_07"
    for name in ("evaluation.json", "benchmark.json", "coverage.json"):
        payload = json.loads((source / name).read_text(encoding="utf-8"))
        if name == "evaluation.json":
            payload["scenario_ids"] = payload["scenario_ids"][:-1]
        (evidence / name).write_text(json.dumps(payload), encoding="utf-8")
    assert verify(tmp_path)["passed"] is False
