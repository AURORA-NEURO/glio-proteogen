"""Independent release verifier for M26-05 evidence and package artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Any

MODULE_ID = "GLIO-PROTEOGEN-M26-05"
CONTRACT_VERSION = "0.1.0-provisional"
AUTHORITY_SHA256 = "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
AUTHORITY_SLICE = "GLIO-PROTEOGEN_240_Module_Dossier.md:9212-9252"
EXPECTED_SCENARIOS = 7
MIN_BRANCH_PERCENT = 95.0
REQUIRED_MEMBERS = (
    "glio_proteogen/contracts/m26_05/v1.py",
    "glio_proteogen/contracts/m26_05/canonical.py",
    "glio_proteogen/modules/c20_biomarker_panel/m26_05_observability_telemetry/engine.py",
    "glio_proteogen/modules/c20_biomarker_panel/m26_05_observability_telemetry/api.py",
    "glio_proteogen/modules/c20_biomarker_panel/m26_05_observability_telemetry/cli.py",
)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"evidence must be an object: {path.name}")  # noqa: TRY003
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _members(path: Path) -> set[str]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return set(archive.namelist())
    with tarfile.open(path, "r:gz") as archive:
        return {member.name for member in archive.getmembers()}


def verify_release(  # noqa: C901, PLR0912
    evidence_dir: Path, wheel: Path | None = None, sdist: Path | None = None
) -> dict[str, Any]:
    errors: list[str] = []
    evaluation = _load(evidence_dir / "evaluation.json")
    benchmark = _load(evidence_dir / "benchmark.json")
    coverage = _load(evidence_dir / "coverage.json")
    package = _load(evidence_dir / "package.json")
    if evaluation.get("moduleId") != MODULE_ID:
        errors.append("evaluation module ID mismatch")
    if evaluation.get("contractVersion") != CONTRACT_VERSION:
        errors.append("evaluation contract version mismatch")
    if evaluation.get("allPassed") is not True or evaluation.get("passed") != EXPECTED_SCENARIOS:
        errors.append("evaluator did not pass all seven scenarios")
    if evaluation.get("authoritySha256", AUTHORITY_SHA256) != AUTHORITY_SHA256:
        errors.append("authority digest mismatch")
    if evaluation.get("authoritySlice", AUTHORITY_SLICE) != AUTHORITY_SLICE:
        errors.append("authority slice mismatch")
    if benchmark.get("moduleId") != MODULE_ID or benchmark.get("budgetPassed") is not True:
        errors.append("benchmark budget failed")
    if float(coverage.get("branchPercent", 0.0)) < MIN_BRANCH_PERCENT:
        errors.append("branch coverage is below 95 percent")
    if package.get("moduleId") != MODULE_ID or package.get("isolatedImport") is not True:
        errors.append("package evidence is incomplete")
    for artifact, expected in (
        (wheel, package.get("wheelSha256")),
        (sdist, package.get("sdistSha256")),
    ):
        if artifact is None:
            continue
        if not artifact.exists():
            errors.append(f"package artifact missing: {artifact}")
        elif _sha256(artifact) != expected:
            errors.append(f"package hash mismatch: {artifact.name}")
        elif not set(REQUIRED_MEMBERS).issubset(_members(artifact)):
            errors.append(f"package members incomplete: {artifact.name}")
    return {
        "moduleId": MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "authoritySha256": AUTHORITY_SHA256,
        "authoritySlice": AUTHORITY_SLICE,
        "verified": not errors,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--sdist", type=Path)
    args = parser.parse_args()
    try:
        report = verify_release(args.evidence_dir, args.wheel, args.sdist)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        report = {"moduleId": MODULE_ID, "verified": False, "errors": [str(error)]}
    sys.stdout.write(json.dumps(report, sort_keys=True, indent=2) + "\n")
    return 0 if report["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
