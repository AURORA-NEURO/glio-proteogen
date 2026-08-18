"""Verify repository-local M10-07 release evidence closure."""

from __future__ import annotations

import hashlib
import json
import sys
import tarfile
from pathlib import Path
from typing import Final
from zipfile import ZipFile

MODULE_ID: Final = "GLIO-PROTEOGEN-M10-07"
EXPECTED_SHA256: Final = "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
EXPECTED_LINES: Final = [3540, 3583]
EXPECTED_EVALUATION_CHECKS: Final = 10


def _archive_names(path: Path) -> list[str]:
    if path.suffix == ".whl":
        with ZipFile(path) as archive:
            return archive.namelist()
    with tarfile.open(path, "r:gz") as archive:
        return archive.getnames()


def verify_release(root: Path = Path()) -> dict[str, object]:
    evidence = root / "release-evidence" / "m10_07"
    traceability = json.loads((evidence / "traceability.json").read_text(encoding="utf-8"))
    release = json.loads((evidence / "release.json").read_text(encoding="utf-8"))
    package = json.loads((evidence / "package.json").read_text(encoding="utf-8"))
    benchmark = json.loads((evidence / "benchmark.json").read_text(encoding="utf-8"))
    evaluation = json.loads((evidence / "evaluation.json").read_text(encoding="utf-8"))
    coverage = json.loads((evidence / "coverage.json").read_text(encoding="utf-8"))
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
        "evaluation": evaluation["module_id"] == MODULE_ID
        and evaluation["authority_sha256"] == EXPECTED_SHA256
        and evaluation["authority_lines"] == EXPECTED_LINES
        and evaluation["checks"] == EXPECTED_EVALUATION_CHECKS
        and evaluation["passed"] is True,
        "coverage": coverage["module_id"] == MODULE_ID
        and coverage["branch_enabled"] is True
        and coverage["passed"] is True
        and coverage["percent_covered"] >= coverage["fail_under_percent"]
        and coverage["percent_branches_covered"] >= coverage["fail_under_percent"]
        and coverage["statements"]
        == coverage["covered_statements"] + coverage["missing_statements"]
        and coverage["branches"] == coverage["covered_branches"] + coverage["missing_branches"],
        "safe_parent_boundary": release["emits_parent"] is False,
        "traceability_csv": (
            root / "docs" / "traceability" / "GLIO-PROTEOGEN-M10-07.csv"
        ).is_file(),
        "package_hashes": all(
            hashlib.sha256((root / item["path"]).read_bytes()).hexdigest() == item["sha256"]
            and (root / item["path"]).stat().st_size == item["bytes"]
            for item in (package["wheel"], package["sdist"])
        ),
        "package_members": all(
            len(_archive_names(root / item["path"])) == item["members"]
            for item in (package["wheel"], package["sdist"])
        ),
        "package_safety_receipt": all(
            item["unsafe_members"] == 0 for item in (package["wheel"], package["sdist"])
        )
        and all(
            not any(
                "__pycache__" in name
                or name.endswith((".pyc", "/.coverage"))
                or "coverage_m10" in name
                or ".m1007-" in name
                for name in _archive_names(root / item["path"])
            )
            for item in (package["wheel"], package["sdist"])
        ),
        "isolated_import": package["isolated_import"] == "passed",
        "benchmark": benchmark["passed"] is True
        and benchmark["mean_ns"] <= benchmark["mean_budget_ns"]
        and benchmark["p95_ns"] <= benchmark["p95_budget_ns"],
    }
    return {"module_id": MODULE_ID, "passed": all(checks.values()), "checks": checks}


if __name__ == "__main__":
    report = verify_release()
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    raise SystemExit(0 if report["passed"] else 1)
