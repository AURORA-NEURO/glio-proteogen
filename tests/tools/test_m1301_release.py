from __future__ import annotations

import copy
import json
from pathlib import Path

from tools.verify_m1301_release import verify_release


def _evidence_path() -> Path:
    return Path(__file__).parents[2] / "release-evidence" / "m13_01"


def test_m1301_release_evidence_verifies() -> None:
    report = verify_release(_evidence_path())
    assert report["module_id"] == "GLIO-PROTEOGEN-M13-01"
    assert report["evaluation"] == "passed"


def test_m1301_release_verifier_rejects_fixture_tampering(tmp_path: Path) -> None:
    source = _evidence_path()
    for name in ("evaluation.json", "benchmark.json", "package.json"):
        (tmp_path / name).write_text((source / name).read_text(encoding="utf-8"), encoding="utf-8")
    payload = json.loads((tmp_path / "evaluation.json").read_text(encoding="utf-8"))
    payload["case_ids"] = list(reversed(payload["case_ids"]))
    (tmp_path / "evaluation.json").write_text(json.dumps(payload), encoding="utf-8")
    try:
        verify_release(tmp_path)
    except ValueError:
        pass
    else:
        raise AssertionError("tampered evaluation unexpectedly verified")  # noqa: TRY003


def test_m1301_release_verifier_rejects_package_tampering(tmp_path: Path) -> None:
    source = _evidence_path()
    for name in ("evaluation.json", "benchmark.json", "package.json"):
        (tmp_path / name).write_text((source / name).read_text(encoding="utf-8"), encoding="utf-8")
    payload = json.loads((tmp_path / "package.json").read_text(encoding="utf-8"))
    forged = copy.deepcopy(payload)
    forged["isolated_import"] = False
    (tmp_path / "package.json").write_text(json.dumps(forged), encoding="utf-8")
    try:
        verify_release(tmp_path)
    except ValueError:
        pass
    else:
        raise AssertionError("tampered package unexpectedly verified")  # noqa: TRY003
