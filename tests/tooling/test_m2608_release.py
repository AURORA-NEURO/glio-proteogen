"""Adversarial tests for the M26-08 release-evidence verifier."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest
import tools.current_candidate_receipt as candidate_receipts
from tools.verify_m2608_release import M2608ReleaseVerificationError, verify_release

from tests.tooling.test_current_candidate_receipt import (
    COMMIT,
    PROFILE,
    _artifacts,
    _receipt_file,
)

EVIDENCE = Path(__file__).parents[2] / "release-evidence" / "m26_08"
FIXTURE = Path(__file__).parents[2] / "tests" / "fixtures" / "m26_08" / "scenarios.json"


def test_m2608_release_evidence_is_closed() -> None:
    verify_release(
        EVIDENCE / "evaluation.json",
        EVIDENCE / "benchmark.json",
        EVIDENCE / "package.json",
        FIXTURE,
    )


def test_m2608_release_evidence_rejects_tampered_authority(tmp_path: Path) -> None:
    payload = json.loads((EVIDENCE / "evaluation.json").read_text(encoding="utf-8"))
    payload["dossier_slice"] = "GLIO-PROTEOGEN_240_Module_Dossier.md:1-2"
    evaluation = tmp_path / "evaluation.json"
    evaluation.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(M2608ReleaseVerificationError, match="dossier_slice"):
        verify_release(evaluation, EVIDENCE / "benchmark.json", EVIDENCE / "package.json", FIXTURE)


def test_m2608_release_evidence_rejects_budget_overrun(tmp_path: Path) -> None:
    payload = json.loads((EVIDENCE / "benchmark.json").read_text(encoding="utf-8"))
    payload["mean_ns"] = payload["mean_budget_ns"] + 1
    benchmark = tmp_path / "benchmark.json"
    benchmark.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(M2608ReleaseVerificationError, match="benchmark exceeds"):
        verify_release(EVIDENCE / "evaluation.json", benchmark, EVIDENCE / "package.json", FIXTURE)


def test_m2608_release_evidence_rejects_incomplete_package(tmp_path: Path) -> None:
    payload = json.loads((EVIDENCE / "package.json").read_text(encoding="utf-8"))
    payload["isolated_import_passed"] = False
    package = tmp_path / "package.json"
    package.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(M2608ReleaseVerificationError, match="isolated_import_passed"):
        verify_release(EVIDENCE / "evaluation.json", EVIDENCE / "benchmark.json", package, FIXTURE)


def test_m2608_release_rejects_non_reproducible_package_receipt(tmp_path: Path) -> None:
    payload = json.loads((EVIDENCE / "package.json").read_text(encoding="utf-8"))
    payload["reproducibility"]["byte_identical"] = False
    package = tmp_path / "package.json"
    package.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(M2608ReleaseVerificationError, match="reproducibility gate"):
        verify_release(EVIDENCE / "evaluation.json", EVIDENCE / "benchmark.json", package, FIXTURE)


def test_m2608_release_rejects_unlocked_build_epoch(tmp_path: Path) -> None:
    payload = json.loads((EVIDENCE / "package.json").read_text(encoding="utf-8"))
    payload["reproducibility"]["source_date_epoch"] = 0
    package = tmp_path / "package.json"
    package.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(M2608ReleaseVerificationError, match="reproducibility gate"):
        verify_release(EVIDENCE / "evaluation.json", EVIDENCE / "benchmark.json", package, FIXTURE)


def test_m2608_release_binds_receipt_to_artifact_bytes(tmp_path: Path) -> None:
    wheel = tmp_path / "glio_proteogen-0.1.0-py3-none-any.whl"
    sdist = tmp_path / "glio_proteogen-0.1.0.tar.gz"
    wheel.write_bytes(b"wheel bytes")
    sdist.write_bytes(b"sdist bytes")
    payload = json.loads((EVIDENCE / "package.json").read_text(encoding="utf-8"))
    payload["wheel"].update(
        {"size_bytes": wheel.stat().st_size, "sha256": sha256(wheel.read_bytes()).hexdigest()}
    )
    payload["sdist"].update(
        {"size_bytes": sdist.stat().st_size, "sha256": sha256(sdist.read_bytes()).hexdigest()}
    )
    payload["reproducibility"].update(
        {
            "wheel_sha256": payload["wheel"]["sha256"],
            "sdist_sha256": payload["sdist"]["sha256"],
        }
    )
    package = tmp_path / "package.json"
    package.write_text(json.dumps(payload), encoding="utf-8")

    verify_release(
        EVIDENCE / "evaluation.json",
        EVIDENCE / "benchmark.json",
        package,
        FIXTURE,
        wheel=wheel,
        sdist=sdist,
    )


def test_m2608_release_rejects_receipt_for_different_artifact(tmp_path: Path) -> None:
    wheel = tmp_path / "glio_proteogen-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"different wheel bytes")

    with pytest.raises(M2608ReleaseVerificationError, match="receipt does not match"):
        verify_release(
            EVIDENCE / "evaluation.json",
            EVIDENCE / "benchmark.json",
            EVIDENCE / "package.json",
            FIXTURE,
            wheel=wheel,
        )


def test_m2608_release_uses_explicit_current_candidate_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wheel, sdist, replay_wheel, replay_sdist = _artifacts(tmp_path)
    receipt = _receipt_file(tmp_path, wheel, sdist, replay_wheel, replay_sdist)
    monkeypatch.setattr(candidate_receipts, "_profile_identity", lambda: PROFILE)

    report = verify_release(
        EVIDENCE / "evaluation.json",
        EVIDENCE / "benchmark.json",
        EVIDENCE / "package.json",
        FIXTURE,
        wheel=wheel,
        sdist=sdist,
        candidate_receipt=receipt,
        expected_source_commit=COMMIT,
    )

    assert report["candidate_receipt"] == str(receipt)


def test_m2608_candidate_mode_still_rejects_tampered_historical_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wheel, sdist, replay_wheel, replay_sdist = _artifacts(tmp_path)
    receipt = _receipt_file(tmp_path, wheel, sdist, replay_wheel, replay_sdist)
    monkeypatch.setattr(candidate_receipts, "_profile_identity", lambda: PROFILE)
    historical = json.loads((EVIDENCE / "package.json").read_text(encoding="utf-8"))
    historical["isolated_import_passed"] = False
    forged = tmp_path / "historical.json"
    forged.write_text(json.dumps(historical), encoding="utf-8")

    with pytest.raises(M2608ReleaseVerificationError, match="isolated_import_passed"):
        verify_release(
            EVIDENCE / "evaluation.json",
            EVIDENCE / "benchmark.json",
            forged,
            FIXTURE,
            wheel=wheel,
            sdist=sdist,
            candidate_receipt=receipt,
            expected_source_commit=COMMIT,
        )


def test_m2608_candidate_mode_rejects_artifact_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wheel, sdist, replay_wheel, replay_sdist = _artifacts(tmp_path)
    receipt = _receipt_file(tmp_path, wheel, sdist, replay_wheel, replay_sdist)
    monkeypatch.setattr(candidate_receipts, "_profile_identity", lambda: PROFILE)
    wheel.write_bytes(wheel.read_bytes() + b"drift")

    with pytest.raises(M2608ReleaseVerificationError, match="current candidate"):
        verify_release(
            EVIDENCE / "evaluation.json",
            EVIDENCE / "benchmark.json",
            EVIDENCE / "package.json",
            FIXTURE,
            wheel=wheel,
            sdist=sdist,
            candidate_receipt=receipt,
            expected_source_commit=COMMIT,
        )
