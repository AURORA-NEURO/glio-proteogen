"""Independent M24-08 release-evidence verifier checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from tools.verify_m2408_release import verify


def test_release_evidence_verifier_accepts_frozen_manifest() -> None:
    report = verify(Path(__file__).parents[2])
    assert report["passed"] is True
    checks = cast("dict[str, bool]", report["checks"])
    assert all(checks.values())


def test_package_evidence_is_machine_readable() -> None:
    path = Path(__file__).parents[2] / "release-evidence" / "m24_08" / "package.json"
    package = json.loads(path.read_text(encoding="utf-8"))
    assert package["module_id"] == "GLIO-PROTEOGEN-M24-08"
    assert package["wheel_sha256"].startswith("b72e833f")
    assert package["sdist_sha256"].startswith("142ef9a8")
