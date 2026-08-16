"""Release-evidence verifier tests for M12-02."""

from __future__ import annotations

import json
from pathlib import Path
from shutil import copyfile

import pytest
from tools.verify_m1202_release import (
    M1202ReleaseVerificationError,
    main,
    verify_release,
)

_DIGEST = "a" * 64
_USAGE_ERROR = 2


def _package() -> dict[str, object]:
    artifact = {"sha256": _DIGEST, "size_bytes": 1, "members": 1}
    return {
        "module_id": "GLIO-PROTEOGEN-M12-02",
        "build_backend": "hatchling",
        "wheel": artifact,
        "sdist": dict(artifact),
        "isolated_import": True,
    }


def _evidence_dir(tmp_path: Path) -> Path:
    destination = tmp_path / "evidence"
    destination.mkdir()
    source = Path(__file__).parents[2] / "release-evidence" / "m12_02"
    copyfile(source / "evaluation.json", destination / "evaluation.json")
    copyfile(source / "benchmark.json", destination / "benchmark.json")
    (destination / "package.json").write_text(json.dumps(_package()), encoding="utf-8")
    return destination


def test_release_verifier_accepts_fixture_bound_evidence(tmp_path: Path) -> None:
    report = verify_release(_evidence_dir(tmp_path))
    assert report["module_id"] == "GLIO-PROTEOGEN-M12-02"
    assert report["evaluation"] == "passed"
    assert report["benchmark"] == "passed"
    assert report["package"] == "passed"


def test_release_verifier_rejects_tampered_case_order(tmp_path: Path) -> None:
    root = _evidence_dir(tmp_path)
    evaluation_path = root / "evaluation.json"
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    evaluation["cases"].reverse()
    evaluation_path.write_text(json.dumps(evaluation), encoding="utf-8")
    with pytest.raises(M1202ReleaseVerificationError):
        verify_release(root)


def test_release_verifier_cli_usage_and_success(tmp_path: Path, capsys) -> None:
    assert main([]) == _USAGE_ERROR
    root = _evidence_dir(tmp_path)
    assert main([str(root)]) == 0
    assert "GLIO-PROTEOGEN-M12-02" in capsys.readouterr().out
