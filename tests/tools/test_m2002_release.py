"""Adversarial checks for the M20-02 release verifier."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from tools.verify_m20_02_release import (
    ReleaseEvidenceError,
    verify_release,
    verify_reproducibility,
    verify_sdist_evidence_boundary,
)


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


def test_m20_02_reproducibility_evidence_requires_byte_identical_rebuilds(
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[2]
    evidence_dir = root / "docs" / "evidence" / "m20_02"
    package = json.loads((evidence_dir / "package.json").read_text(encoding="utf-8"))
    verify_reproducibility(evidence_dir / "reproducibility.json", package)

    forged = tmp_path / "reproducibility.json"
    report = json.loads((evidence_dir / "reproducibility.json").read_text(encoding="utf-8"))
    report["sdist"]["sha256"][1] = "0" * 64
    forged.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ReleaseEvidenceError, match="sdist rebuild hashes disagree"):
        verify_reproducibility(forged, package)

    report["source_commit"] = "not-a-commit"
    forged.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ReleaseEvidenceError, match="invalid source_commit"):
        verify_reproducibility(forged, package)


def test_m20_02_sdist_excludes_mutable_release_records() -> None:
    root = Path(__file__).parents[2]
    verify_sdist_evidence_boundary(root / "dist" / "glio_proteogen-0.1.0.tar.gz")
