"""Verify repository-local M10-07 release evidence closure."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Final

MODULE_ID: Final = "GLIO-PROTEOGEN-M10-07"
EXPECTED_SHA256: Final = "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
EXPECTED_LINES: Final = [3540, 3583]


def verify_release(root: Path = Path()) -> dict[str, object]:
    evidence = root / "release-evidence" / "m10_07"
    traceability = json.loads((evidence / "traceability.json").read_text(encoding="utf-8"))
    release = json.loads((evidence / "release.json").read_text(encoding="utf-8"))
    fixture = json.loads(
        (root / "tests" / "fixtures" / "m10_07" / "scenarios.json").read_text(encoding="utf-8")
    )
    checks = {
        "module_id": traceability["module_id"]
        == MODULE_ID
        == release["module_id"]
        == fixture["module_id"],
        "authority_sha256": traceability["dossier_sha256"]
        == EXPECTED_SHA256
        == fixture["authority"]["dossier_sha256"],
        "authority_lines": traceability["dossier_lines"]
        == EXPECTED_LINES
        == fixture["authority"]["lines"],
        "provisional_abi": traceability["provisional_abi"] is True
        and release["contract_version"].endswith("provisional"),
        "safe_parent_boundary": release["emits_parent"] is False,
        "traceability_csv": (
            root / "docs" / "traceability" / "GLIO-PROTEOGEN-M10-07.csv"
        ).is_file(),
    }
    return {"module_id": MODULE_ID, "passed": all(checks.values()), "checks": checks}


if __name__ == "__main__":
    report = verify_release()
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    raise SystemExit(0 if report["passed"] else 1)
