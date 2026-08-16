"""Verify M11-08 release evidence without trusting generated summaries."""

# The verifier deliberately reports precise, user-facing failure messages and
# compares a small number of fixed release invariants. Keep those checks
# explicit rather than hiding them behind generic assertion machinery.
# ruff: noqa: TRY003, PLR2004

from __future__ import annotations

import hashlib
import json
import tarfile
import zipfile
from math import ceil
from pathlib import Path
from statistics import mean, median
from typing import Final, cast

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.strict_json import strict_json_loads

MODULE: Final = "GLIO-PROTEOGEN-M11-08"
AUTHORITY_SHA256: Final = "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
AUTHORITY_LINES: Final = "3944-3987"
EXPECTED_SCENARIOS: Final = 9
EXPECTED_TESTS: Final = 43
COVERAGE_THRESHOLD: Final = 95.0
ROOT: Final = Path(__file__).resolve().parents[1]
EVIDENCE: Final = ROOT / "release-evidence" / "m11_08"


class M1108ReleaseVerificationError(ValueError):
    """Raised when release evidence is stale, incomplete or contradictory."""


def _load(name: str) -> dict[str, object]:
    path = EVIDENCE / name
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise M1108ReleaseVerificationError(f"cannot load {name}") from error
    if not isinstance(value, dict):
        raise M1108ReleaseVerificationError(f"{name} must contain an object")
    return cast("dict[str, object]", value)


def _assert_header(document: dict[str, object]) -> None:
    if document.get("module") != MODULE:
        raise M1108ReleaseVerificationError("release evidence module mismatch")
    if document.get("authority_sha256") != AUTHORITY_SHA256:
        raise M1108ReleaseVerificationError("authority digest mismatch")
    if document.get("authority_lines") != AUTHORITY_LINES:
        raise M1108ReleaseVerificationError("authority line range mismatch")


def _verify_evaluation() -> dict[str, object]:
    document = _load("evaluation.json")
    _assert_header(document)
    fixture_path = ROOT / "tests" / "fixtures" / "m11_08" / "scenarios.json"
    fixture = strict_json_loads(fixture_path.read_bytes())
    if document.get("fixture_sha256") != sha256_digest(fixture):
        raise M1108ReleaseVerificationError("fixture digest mismatch")
    checks = document.get("checks")
    if not isinstance(checks, dict) or not all(checks.values()):
        raise M1108ReleaseVerificationError("evaluator checks are not all true")
    if (
        document.get("declared_scenarios") != EXPECTED_SCENARIOS
        or document.get("executed_scenarios") != EXPECTED_SCENARIOS
    ):
        raise M1108ReleaseVerificationError("evaluator scenario count mismatch")
    if document.get("passed") is not True:
        raise M1108ReleaseVerificationError("evaluator did not pass")
    return document


def _verify_benchmark() -> dict[str, object]:  # noqa: C901
    document = _load("benchmark.json")
    _assert_header(document)
    samples = document.get("samples_ns")
    if (
        not isinstance(samples, list)
        or not samples
        or not all(isinstance(value, int) and value >= 0 for value in samples)
    ):
        raise M1108ReleaseVerificationError("benchmark samples are invalid")
    values = cast("list[int]", samples)
    if document.get("iterations") != len(values):
        raise M1108ReleaseVerificationError("benchmark iteration count mismatch")
    if document.get("mean_ns") != int(mean(values)):
        raise M1108ReleaseVerificationError("benchmark mean is not reproducible")
    if document.get("median_ns") != int(median(values)):
        raise M1108ReleaseVerificationError("benchmark median is not reproducible")
    p95 = sorted(values)[max(0, ceil(0.95 * len(values)) - 1)]
    if document.get("p95_ns") != p95:
        raise M1108ReleaseVerificationError("benchmark p95 is not reproducible")
    if not isinstance(document.get("mean_budget_ns"), int) or not isinstance(
        document.get("p95_budget_ns"), int
    ):
        raise M1108ReleaseVerificationError("benchmark budgets are invalid")
    mean_ns = document.get("mean_ns")
    mean_budget_ns = document.get("mean_budget_ns")
    p95_ns = document.get("p95_ns")
    p95_budget_ns = document.get("p95_budget_ns")
    if not all(
        isinstance(value, int)
        for value in (mean_ns, mean_budget_ns, p95_ns, p95_budget_ns)
    ):
        raise M1108ReleaseVerificationError("benchmark numeric fields are invalid")
    mean_ns = cast("int", mean_ns)
    mean_budget_ns = cast("int", mean_budget_ns)
    p95_ns = cast("int", p95_ns)
    p95_budget_ns = cast("int", p95_budget_ns)
    if mean_ns > mean_budget_ns:
        raise M1108ReleaseVerificationError("benchmark mean budget exceeded")
    if p95_ns > p95_budget_ns:
        raise M1108ReleaseVerificationError("benchmark p95 budget exceeded")
    if document.get("passed") is not True:
        raise M1108ReleaseVerificationError("benchmark did not pass")
    return document


def _verify_coverage() -> dict[str, object]:
    document = _load("coverage.json")
    _assert_header(document)
    branch_percent = document.get("branch_percent")
    combined_percent = document.get("combined_percent")
    if not isinstance(branch_percent, (int, float)) or not isinstance(
        combined_percent, (int, float)
    ):
        raise M1108ReleaseVerificationError("coverage percentages are invalid")
    if float(branch_percent) < COVERAGE_THRESHOLD:
        raise M1108ReleaseVerificationError("branch coverage is below 95 percent")
    if float(combined_percent) < COVERAGE_THRESHOLD:
        raise M1108ReleaseVerificationError("combined coverage is below 95 percent")
    if document.get("tests_passed") != EXPECTED_TESTS or document.get("passed") is not True:
        raise M1108ReleaseVerificationError("coverage evidence is incomplete")
    return document


def _artifact_digest(path: Path) -> tuple[int, str]:
    data = path.read_bytes()
    return len(data), hashlib.sha256(data).hexdigest()


def _member_count(path: Path) -> int:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return len(archive.namelist())
    with tarfile.open(path, "r:gz") as archive:
        return len(archive.getnames())


def _verify_package() -> dict[str, object]:
    document = _load("package.json")
    _assert_header(document)
    artifacts = document.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 2:
        raise M1108ReleaseVerificationError(
            "package artifact inventory must contain wheel and sdist"
        )
    for item in artifacts:
        if not isinstance(item, dict):
            raise M1108ReleaseVerificationError("package artifact entry is invalid")
        name = item.get("name")
        if not isinstance(name, str):
            raise M1108ReleaseVerificationError("package artifact name is invalid")
        path = ROOT / "dist-m11_08" / name
        if not path.is_file():
            raise M1108ReleaseVerificationError(f"package artifact missing: {name}")
        size, digest = _artifact_digest(path)
        if item.get("bytes") != size or item.get("sha256") != digest:
            raise M1108ReleaseVerificationError(f"package hash mismatch: {name}")
        if item.get("members") != _member_count(path):
            raise M1108ReleaseVerificationError(f"package member count mismatch: {name}")
    isolated = document.get("isolated_install")
    if not isinstance(isolated, dict) or isolated.get("import_check") != "passed":
        raise M1108ReleaseVerificationError("isolated package import did not pass")
    if document.get("passed") is not True:
        raise M1108ReleaseVerificationError("package evidence did not pass")
    return document


def verify_release() -> dict[str, object]:
    """Return a compact verified release report or raise on the first mismatch."""

    evaluation = _verify_evaluation()
    benchmark = _verify_benchmark()
    coverage = _verify_coverage()
    package = _verify_package()
    return {
        "module": MODULE,
        "authority_sha256": AUTHORITY_SHA256,
        "authority_lines": AUTHORITY_LINES,
        "evaluation": evaluation,
        "benchmark": benchmark,
        "coverage": coverage,
        "package": package,
        "passed": True,
    }


def main() -> int:
    try:
        report = verify_release()
    except M1108ReleaseVerificationError as error:
        print(json.dumps({"passed": False, "error": str(error)}, sort_keys=True))  # noqa: T201
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
