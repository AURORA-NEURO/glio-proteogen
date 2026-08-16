"""Release evidence verifier tests for M11-07."""

from pathlib import Path

import pytest
import tools.verify_m1107_release as verifier
from tools.verify_m1107_release import (
    M1107ReleaseVerificationError,
    verify_release,
)


def test_release_evidence_closes_without_artifacts() -> None:
    report = verify_release()
    assert report["module_id"] == "GLIO-PROTEOGEN-M11-07"
    assert report["artifact_checks"] is False


def test_release_evidence_verifies_built_artifacts() -> None:
    output = Path(r"C:\Users\murar\AppData\Local\Temp\gpa-m1107-release-final4")
    report = verify_release(
        wheel=output / "glio_proteogen-0.1.0-py3-none-any.whl",
        sdist=output / "glio_proteogen-0.1.0.tar.gz",
    )
    assert report["artifact_checks"] is True


def test_release_verifier_rejects_tampered_benchmark(monkeypatch) -> None:
    original = verifier._read

    def tampered(name: str) -> dict[str, object]:
        value = original(name)
        if name == "benchmark.json":
            value["within_budget"] = False
        return value

    monkeypatch.setattr(verifier, "_read", tampered)
    with pytest.raises(M1107ReleaseVerificationError, match="budget"):
        verifier.verify_release()
