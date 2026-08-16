"""Adversarial checks for the M20-02 release verifier."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from tools.verify_m20_02_release import ReleaseEvidenceError, verify_release


def test_m20_02_release_verifier_accepts_locked_reports() -> None:
    root = Path(__file__).parents[2]
    verify_release(
        root / "docs" / "evidence" / "m20_02",
        root / "dist" / "glio_proteogen-0.1.0-py3-none-any.whl",
        root / "dist" / "glio_proteogen-0.1.0.tar.gz",
    )


def test_m20_02_release_verifier_rejects_tampered_evaluation(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    source = root / "docs" / "evidence" / "m20_02"
    evidence = tmp_path / "m20_02"
    evidence.mkdir()
    for path in source.glob("*.json"):
        shutil.copy2(path, evidence / path.name)
    evaluation = json.loads((evidence / "evaluation.json").read_text(encoding="utf-8"))
    evaluation["passed"] = False
    (evidence / "evaluation.json").write_text(json.dumps(evaluation), encoding="utf-8")
    with pytest.raises(ReleaseEvidenceError):
        verify_release(
            evidence,
            root / "dist" / "glio_proteogen-0.1.0-py3-none-any.whl",
            root / "dist" / "glio_proteogen-0.1.0.tar.gz",
        )
