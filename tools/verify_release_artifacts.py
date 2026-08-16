# ruff: noqa: TRY003
"""Verify that release evidence describes and tests the exact built wheel.

The checks are intentionally standard-library only so they can run inside the pristine
runtime environment created from a candidate wheel.  They do not qualify a release; they
only reject internally inconsistent build evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import math
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from email.parser import BytesParser
from email.policy import default
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING
from urllib.parse import urlsplit
from urllib.request import url2pathname
from zipfile import BadZipFile, ZipFile

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

_PROJECT_NAME = "glio-proteogen"
_PACKAGE_NAME = "glio_proteogen"
_CONSOLE_SCRIPT = "glio-proteogen"
_CONSOLE_ENTRY_POINT = "glio_proteogen.adapters.cli:app"
_SCHEMA_URI = "https://json-schema.org/draft/2020-12/schema"
_M0403_MODULE_ID = "GLIO-PROTEOGEN-M04-03"
_M0403_CASE_COUNT = 72
_M0403_BENCHMARK_ITERATIONS = 25
_M0403_BENCHMARK_WARMUPS = 1
_M0403_MEAN_BUDGET_NS = 500_000_000
_M0403_P95_BUDGET_NS = 750_000_000
_M0404_MODULE_ID = "GLIO-PROTEOGEN-M04-04"
_M0404_CASE_COUNT = 72
_M0404_BENCHMARK_ITERATIONS = 25
_M0404_BENCHMARK_WARMUPS = 1
_M0404_MEAN_BUDGET_NS = 500_000_000
_M0404_P95_BUDGET_NS = 750_000_000
_M0404_BENCHMARK_SHAPE = {
    "role_count": 4,
    "profile_count": 32,
    "threshold_count": 256,
    "fact_count": 4,
    "metric_count": 32,
    "evidence_count": 45,
    "limitation_count": 3,
}
_M1904_MODULE_ID = "GLIO-PROTEOGEN-M19-04"
_M1904_SCENARIO_COUNT = 9
_M1904_ADVERSARIAL_CASE_COUNT = 8
_M1904_ADVERSARIAL_COVERAGE_PERCENT = 100.0
_M1904_BENCHMARK_ITERATIONS = 25
_M1904_BENCHMARK_WARMUPS = 1
_M1904_MEAN_BUDGET_NS = 500_000_000
_M1904_P95_BUDGET_NS = 750_000_000
_M2604_MODULE_ID = "GLIO-PROTEOGEN-M26-04"
_M2604_CASE_COUNT = 8
_M2604_SCHEMA_COUNT = 12
_M2604_UNCERTAINTY_DIMENSIONS = 7
_M2604_BENCHMARK_ITERATIONS = 10
_M2604_MEAN_BUDGET_NS = 500_000_000
_M2604_P95_BUDGET_NS = 750_000_000
_M2607_MODULE_ID = "GLIO-PROTEOGEN-M26-07"
_M2607_CASE_COUNT = 8
_M2607_SCHEMA_COUNT = 8
_M2607_BENCHMARK_ITERATIONS = 10
_M2607_MEAN_BUDGET_NS = 500_000_000
_M2607_P95_BUDGET_NS = 750_000_000
_M2607_DOSSIER_SHA256 = "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
_M2607_DOSSIER_SLICE = "GLIO-PROTEOGEN_240_Module_Dossier.md:9300-9340"
_CLI_SCHEMA_SMOKE_TESTS = (
    (
        ("export-schema", "protocol-schema"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M01-01:1.0.0:protocol-schema",
    ),
    (
        ("identity", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M01-02:1.0.0:request",
    ),
    (
        ("raw", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M01-03:1.0.0:request",
    ),
    (
        ("quality", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M01-04:1.0.0:request",
    ),
    (
        ("artifact", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M01-05:1.0.0:request",
    ),
    (
        ("harmonize", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M01-06:1.0.0:request",
    ),
    (
        ("support", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M01-07:1.0.0:request",
    ),
    (
        ("release", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M01-08:1.0.0:request",
    ),
    (
        ("identification", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-01:1.0.0:request",
    ),
    (
        ("binding", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-02:1.0.0:request",
    ),
    (
        ("identification-raw", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-03:1.0.0:request",
    ),
    (
        ("identification-quality", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-04:1.0.0:request",
    ),
    (
        ("identification-artifacts", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-05:1.0.0:request",
    ),
    (
        ("identification-harmonization", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-06:1.0.0:request",
    ),
    (
        ("identification-support", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-07:1.0.0:request",
    ),
    (
        ("identification-release", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-08:1.0.0:request",
    ),
    (
        ("protein-inference-protocol", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M03-01:1.0.0:request",
    ),
    (
        ("protein-inference-lineage", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M03-02:1.0.0:request",
    ),
    (
        ("protein-inference-raw", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M03-03:1.0.0:request",
    ),
    (
        ("protein-inference-quality", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M03-04:1.0.0:request",
    ),
    (
        ("protein-inference-artifacts", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M03-05:1.0.0:request",
    ),
    (
        ("protein-inference-harmonization", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M03-06:1.0.0:request",
    ),
    (
        ("protein-inference-support", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M03-07:1.0.0:request",
    ),
    (
        ("protein-inference-release", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M03-08:1.0.0:request",
    ),
    (
        ("proteoform-protocol", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M04-01:1.0.0:request",
    ),
    (
        ("proteoform-lineage", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M04-02:1.0.0:request",
    ),
    (
        ("proteoform-raw", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M04-03:1.0.0:request",
    ),
    (
        ("proteoform-quality", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M04-04:1.0.0:request",
    ),
)
_FORBIDDEN_RUNTIME_COMPONENTS = frozenset(
    {
        "cyclonedx-bom",
        "hypothesis",
        "mypy",
        "pip-audit",
        "pytest",
        "pytest-benchmark",
        "pytest-cov",
        "pytest-xdist",
        "ruff",
    }
)


class ReleaseArtifactError(ValueError):
    """Raised when candidate release evidence is incomplete or inconsistent."""


@dataclass(frozen=True, slots=True)
class WheelIdentity:
    """Distribution identity read from a wheel's embedded core metadata."""

    name: str
    version: str
    filename: str
    sha256: str


@dataclass(frozen=True, slots=True)
class RuntimeSbomSummary:
    """Verified root identity and component count for a runtime SBOM."""

    root_name: str
    root_version: str
    component_count: int


def _normalized_distribution_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).casefold()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def wheel_identity(wheel: Path) -> WheelIdentity:
    """Read the one authoritative Name/Version pair embedded in *wheel*."""

    if not wheel.is_file() or wheel.suffix != ".whl":
        raise ReleaseArtifactError("candidate wheel path is not one wheel file")
    try:
        with ZipFile(wheel) as archive:
            metadata_paths = tuple(
                name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
            )
            if len(metadata_paths) != 1:
                raise ReleaseArtifactError("candidate wheel must contain one METADATA file")
            message = BytesParser(policy=default).parsebytes(archive.read(metadata_paths[0]))
    except (BadZipFile, KeyError, OSError) as error:
        raise ReleaseArtifactError("candidate wheel cannot be read safely") from error

    name = message.get("Name")
    version = message.get("Version")
    if not isinstance(name, str) or not name.strip():
        raise ReleaseArtifactError("candidate wheel has no distribution name")
    if not isinstance(version, str) or not version.strip():
        raise ReleaseArtifactError("candidate wheel has no distribution version")
    if _normalized_distribution_name(name) != _PROJECT_NAME:
        raise ReleaseArtifactError("candidate wheel is not the expected project")
    return WheelIdentity(
        name=name,
        version=version,
        filename=wheel.name,
        sha256=_sha256(wheel),
    )


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ReleaseArtifactError(f"release evidence {label} must be an object")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ReleaseArtifactError(f"release evidence {label} must be an array")
    return value


def _load_sbom(path: Path) -> Mapping[str, object]:
    try:
        payload: object = json.loads(path.read_bytes())
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as error:
        raise ReleaseArtifactError("runtime SBOM is not valid UTF-8 JSON") from error
    return _mapping(payload, "document")


def _load_json_evidence(path: Path, label: str) -> Mapping[str, object]:
    try:
        payload: object = json.loads(path.read_bytes())
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as error:
        raise ReleaseArtifactError(f"{label} is not valid UTF-8 JSON") from error
    return _mapping(payload, label)


def _require_exact_integer(
    document: Mapping[str, object],
    field: str,
    expected: int,
    label: str,
) -> None:
    value = document.get(field)
    if type(value) is not int or value != expected:
        raise ReleaseArtifactError(f"{label} has an unexpected {field}")


def _require_empty_array(document: Mapping[str, object], field: str, label: str) -> None:
    if _sequence(document.get(field), f"{label} {field}"):
        raise ReleaseArtifactError(f"{label} has nonempty {field}")


def _verify_m0403_evaluation(evaluation_report: Mapping[str, object]) -> None:
    if evaluation_report.get("module_id") != _M0403_MODULE_ID:
        raise ReleaseArtifactError("M04-03 evaluation report has the wrong module identity")
    if evaluation_report.get("passed") is not True:
        raise ReleaseArtifactError("M04-03 evaluation report did not pass")
    _require_exact_integer(
        evaluation_report,
        "declared_case_count",
        _M0403_CASE_COUNT,
        "M04-03 evaluation report",
    )
    _require_exact_integer(
        evaluation_report,
        "executed_case_count",
        _M0403_CASE_COUNT,
        "M04-03 evaluation report",
    )
    for field in ("missing_case_ids", "extra_case_ids", "duplicated_case_ids"):
        _require_empty_array(evaluation_report, field, "M04-03 evaluation report")
    checks = _sequence(evaluation_report.get("checks"), "M04-03 evaluation checks")
    if any(
        _mapping(check, "M04-03 evaluation check").get("passed") is not True for check in checks
    ):
        raise ReleaseArtifactError("M04-03 evaluation report contains a failed check")
    scenario_names = tuple(
        name
        for check in checks
        if isinstance((name := _mapping(check, "M04-03 evaluation check").get("name")), str)
        and name.startswith("scenario.")
    )
    if len(scenario_names) != _M0403_CASE_COUNT or len(set(scenario_names)) != len(scenario_names):
        raise ReleaseArtifactError("M04-03 evaluation report lacks exact scenario closure")


def _verify_m0403_benchmark(benchmark_report: Mapping[str, object]) -> None:
    if benchmark_report.get("module_id") != _M0403_MODULE_ID:
        raise ReleaseArtifactError("M04-03 benchmark report has the wrong module identity")
    if benchmark_report.get("passed") is not True:
        raise ReleaseArtifactError("M04-03 benchmark report did not pass")
    for field, expected in (
        ("iterations", _M0403_BENCHMARK_ITERATIONS),
        ("warmup_count", _M0403_BENCHMARK_WARMUPS),
        ("mean_budget_ns", _M0403_MEAN_BUDGET_NS),
        ("p95_budget_ns", _M0403_P95_BUDGET_NS),
    ):
        _require_exact_integer(benchmark_report, field, expected, "M04-03 benchmark report")
    mean = benchmark_report.get("mean_ns")
    p95 = benchmark_report.get("p95_ns")
    if isinstance(mean, bool) or not isinstance(mean, (int, float)):
        raise ReleaseArtifactError("M04-03 benchmark report has an invalid mean")
    if isinstance(p95, bool) or not isinstance(p95, int):
        raise ReleaseArtifactError("M04-03 benchmark report has an invalid p95")
    if (
        not math.isfinite(mean)
        or mean < 0
        or mean > _M0403_MEAN_BUDGET_NS
        or p95 < 0
        or p95 > _M0403_P95_BUDGET_NS
    ):
        raise ReleaseArtifactError("M04-03 benchmark report exceeds its timing budgets")


def verify_m0403_evidence(evaluation: Path, benchmark: Path) -> None:
    """Verify the archived M04-03 corpus closure and benchmark budgets."""

    _verify_m0403_evaluation(_load_json_evidence(evaluation, "M04-03 evaluation report"))
    _verify_m0403_benchmark(_load_json_evidence(benchmark, "M04-03 benchmark report"))


def _verify_m0404_evaluation(evaluation_report: Mapping[str, object]) -> None:
    if evaluation_report.get("module_id") != _M0404_MODULE_ID:
        raise ReleaseArtifactError("M04-04 evaluation report has the wrong module identity")
    if evaluation_report.get("passed") is not True:
        raise ReleaseArtifactError("M04-04 evaluation report did not pass")
    for field in ("declared_case_count", "executed_case_count"):
        _require_exact_integer(
            evaluation_report,
            field,
            _M0404_CASE_COUNT,
            "M04-04 evaluation report",
        )
    for field in ("missing_case_ids", "extra_case_ids", "duplicated_case_ids"):
        _require_empty_array(evaluation_report, field, "M04-04 evaluation report")
    checks = _sequence(evaluation_report.get("checks"), "M04-04 evaluation checks")
    if any(
        _mapping(check, "M04-04 evaluation check").get("passed") is not True for check in checks
    ):
        raise ReleaseArtifactError("M04-04 evaluation report contains a failed check")
    scenario_names = tuple(
        name
        for check in checks
        if isinstance((name := _mapping(check, "M04-04 evaluation check").get("name")), str)
        and name.startswith("scenario.")
    )
    if len(scenario_names) != _M0404_CASE_COUNT or len(set(scenario_names)) != len(scenario_names):
        raise ReleaseArtifactError("M04-04 evaluation report lacks exact scenario closure")


def _verify_m0404_benchmark(benchmark_report: Mapping[str, object]) -> None:
    if benchmark_report.get("module_id") != _M0404_MODULE_ID:
        raise ReleaseArtifactError("M04-04 benchmark report has the wrong module identity")
    if benchmark_report.get("passed") is not True:
        raise ReleaseArtifactError("M04-04 benchmark report did not pass")
    exact_fields = {
        "iterations": _M0404_BENCHMARK_ITERATIONS,
        "warmup_count": _M0404_BENCHMARK_WARMUPS,
        "mean_budget_ns": _M0404_MEAN_BUDGET_NS,
        "p95_budget_ns": _M0404_P95_BUDGET_NS,
        **_M0404_BENCHMARK_SHAPE,
    }
    for field, expected in exact_fields.items():
        _require_exact_integer(benchmark_report, field, expected, "M04-04 benchmark report")
    mean = benchmark_report.get("mean_ns")
    p95 = benchmark_report.get("p95_ns")
    if isinstance(mean, bool) or not isinstance(mean, (int, float)):
        raise ReleaseArtifactError("M04-04 benchmark report has an invalid mean")
    if isinstance(p95, bool) or not isinstance(p95, int):
        raise ReleaseArtifactError("M04-04 benchmark report has an invalid p95")
    if (
        not math.isfinite(mean)
        or mean < 0
        or mean > _M0404_MEAN_BUDGET_NS
        or p95 < 0
        or p95 > _M0404_P95_BUDGET_NS
    ):
        raise ReleaseArtifactError("M04-04 benchmark report exceeds its timing budgets")


def verify_m0404_evidence(evaluation: Path, benchmark: Path) -> None:
    """Verify the archived M04-04 corpus closure, maximum shape, and timing budgets."""

    _verify_m0404_evaluation(_load_json_evidence(evaluation, "M04-04 evaluation report"))
    _verify_m0404_benchmark(_load_json_evidence(benchmark, "M04-04 benchmark report"))


def _verify_m1904_evaluation(evaluation_report: Mapping[str, object]) -> None:
    if evaluation_report.get("module_id") != _M1904_MODULE_ID:
        raise ReleaseArtifactError("M19-04 evaluation report has the wrong module identity")
    if evaluation_report.get("passed") is not True:
        raise ReleaseArtifactError("M19-04 evaluation report did not pass")
    _require_exact_integer(
        evaluation_report,
        "scenario_count",
        _M1904_SCENARIO_COUNT,
        "M19-04 evaluation report",
    )
    _require_exact_integer(
        evaluation_report,
        "adversarial_case_count",
        _M1904_ADVERSARIAL_CASE_COUNT,
        "M19-04 evaluation report",
    )
    _require_exact_integer(
        evaluation_report,
        "adversarial_passed_count",
        _M1904_ADVERSARIAL_CASE_COUNT,
        "M19-04 evaluation report",
    )
    if evaluation_report.get("adversarial_coverage_percent") != _M1904_ADVERSARIAL_COVERAGE_PERCENT:
        raise ReleaseArtifactError("M19-04 adversarial coverage is incomplete")
    checks = _sequence(evaluation_report.get("checks"), "M19-04 evaluation checks")
    if not checks or any(
        _mapping(check, "M19-04 evaluation check").get("passed") is not True for check in checks
    ):
        raise ReleaseArtifactError("M19-04 evaluation report contains a failed check")
    if not any(
        _mapping(check, "M19-04 evaluation check").get("name") == "corpus.executable_oracles"
        for check in checks
    ):
        raise ReleaseArtifactError("M19-04 evaluation report lacks executable oracle closure")


def _verify_m1904_benchmark(benchmark_report: Mapping[str, object]) -> None:
    if benchmark_report.get("module_id") != _M1904_MODULE_ID:
        raise ReleaseArtifactError("M19-04 benchmark report has the wrong module identity")
    if benchmark_report.get("passed") is not True:
        raise ReleaseArtifactError("M19-04 benchmark report did not pass")
    for field, expected in (
        ("iterations", _M1904_BENCHMARK_ITERATIONS),
        ("warmup_count", _M1904_BENCHMARK_WARMUPS),
        ("mean_budget_ns", _M1904_MEAN_BUDGET_NS),
        ("p95_budget_ns", _M1904_P95_BUDGET_NS),
    ):
        _require_exact_integer(benchmark_report, field, expected, "M19-04 benchmark report")
    mean = benchmark_report.get("mean_ns")
    p95 = benchmark_report.get("p95_ns")
    if isinstance(mean, bool) or not isinstance(mean, (int, float)):
        raise ReleaseArtifactError("M19-04 benchmark report has an invalid mean")
    if isinstance(p95, bool) or not isinstance(p95, int):
        raise ReleaseArtifactError("M19-04 benchmark report has an invalid p95")
    if (
        not math.isfinite(mean)
        or mean < 0
        or mean > _M1904_MEAN_BUDGET_NS
        or p95 < 0
        or p95 > _M1904_P95_BUDGET_NS
    ):
        raise ReleaseArtifactError("M19-04 benchmark report exceeds its timing budgets")


def verify_m1904_evidence(evaluation: Path, benchmark: Path) -> None:
    """Verify M19-04 scenario closure, adversarial coverage, and timing budgets."""

    _verify_m1904_evaluation(_load_json_evidence(evaluation, "M19-04 evaluation report"))
    _verify_m1904_benchmark(_load_json_evidence(benchmark, "M19-04 benchmark report"))


def _verify_m2604_evaluation(evaluation_report: Mapping[str, object]) -> None:
    if evaluation_report.get("moduleId") != _M2604_MODULE_ID:
        raise ReleaseArtifactError("M26-04 evaluation report has the wrong module identity")
    if evaluation_report.get("passed") is not True:
        raise ReleaseArtifactError("M26-04 evaluation report did not pass")
    for field, expected in (
        ("scenarioCount", _M2604_CASE_COUNT),
        ("passedCases", _M2604_CASE_COUNT),
        ("schemaCount", _M2604_SCHEMA_COUNT),
        ("uncertaintyDimensions", _M2604_UNCERTAINTY_DIMENSIONS),
    ):
        _require_exact_integer(evaluation_report, field, expected, "M26-04 evaluation report")
    cases = _sequence(evaluation_report.get("cases"), "M26-04 evaluation cases")
    if len(cases) != _M2604_CASE_COUNT or any(not isinstance(case, str) for case in cases):
        raise ReleaseArtifactError("M26-04 evaluation report lacks exact scenario closure")
    if evaluation_report.get("replayTamperRejected") is not True:
        raise ReleaseArtifactError("M26-04 evaluation report lacks tamper rejection")
    if evaluation_report.get("deterministicRepeat") is not True:
        raise ReleaseArtifactError("M26-04 evaluation report lacks deterministic replay")


def _verify_m2604_benchmark(benchmark_report: Mapping[str, object]) -> None:
    if benchmark_report.get("moduleId") != _M2604_MODULE_ID:
        raise ReleaseArtifactError("M26-04 benchmark report has the wrong module identity")
    if benchmark_report.get("passed") is not True:
        raise ReleaseArtifactError("M26-04 benchmark report did not pass")
    _require_exact_integer(
        benchmark_report, "iterations", _M2604_BENCHMARK_ITERATIONS, "M26-04 benchmark report"
    )
    budgets = _mapping(benchmark_report.get("budgetsNs"), "M26-04 benchmark budgets")
    _require_exact_integer(budgets, "mean", _M2604_MEAN_BUDGET_NS, "M26-04 benchmark budgets")
    _require_exact_integer(budgets, "p95", _M2604_P95_BUDGET_NS, "M26-04 benchmark budgets")
    samples = _sequence(benchmark_report.get("samplesNs"), "M26-04 benchmark samples")
    if len(samples) != _M2604_BENCHMARK_ITERATIONS or any(
        type(sample) is not int or sample < 0 for sample in samples
    ):
        raise ReleaseArtifactError("M26-04 benchmark report has invalid samples")
    mean = benchmark_report.get("meanNs")
    p95 = benchmark_report.get("p95Ns")
    if type(mean) is not int or type(p95) is not int:
        raise ReleaseArtifactError("M26-04 benchmark report has invalid summary values")
    if mean > _M2604_MEAN_BUDGET_NS or p95 > _M2604_P95_BUDGET_NS:
        raise ReleaseArtifactError("M26-04 benchmark report exceeds its timing budgets")


def verify_m2604_evidence(evaluation: Path, benchmark: Path) -> None:
    """Verify M26-04 scenario closure and locked gateway timing budgets."""

    _verify_m2604_evaluation(_load_json_evidence(evaluation, "M26-04 evaluation report"))
    _verify_m2604_benchmark(_load_json_evidence(benchmark, "M26-04 benchmark report"))


def _verify_m2607_evaluation(evaluation_report: Mapping[str, object]) -> None:
    if evaluation_report.get("moduleId") != _M2607_MODULE_ID:
        raise ReleaseArtifactError("M26-07 evaluation report has the wrong module identity")
    if evaluation_report.get("passed") is not True:
        raise ReleaseArtifactError("M26-07 evaluation report did not pass")
    authority = _mapping(evaluation_report.get("authority"), "M26-07 authority")
    if (
        authority.get("dossierSha256") != _M2607_DOSSIER_SHA256
        or authority.get("slice") != _M2607_DOSSIER_SLICE
    ):
        raise ReleaseArtifactError("M26-07 evaluation authority is not locked")
    for field, expected in (
        ("scenarioCount", _M2607_CASE_COUNT),
        ("passedCases", _M2607_CASE_COUNT),
        ("schemaCount", _M2607_SCHEMA_COUNT),
        ("uncertaintyDimensions", 7),
    ):
        _require_exact_integer(evaluation_report, field, expected, "M26-07 evaluation report")
    cases = _sequence(evaluation_report.get("cases"), "M26-07 evaluation cases")
    if len(cases) != _M2607_CASE_COUNT or len(set(cases)) != _M2607_CASE_COUNT:
        raise ReleaseArtifactError("M26-07 evaluation report lacks exact scenario closure")


def _verify_m2607_benchmark(benchmark_report: Mapping[str, object]) -> None:
    if benchmark_report.get("moduleId") != _M2607_MODULE_ID:
        raise ReleaseArtifactError("M26-07 benchmark report has the wrong module identity")
    if benchmark_report.get("passed") is not True:
        raise ReleaseArtifactError("M26-07 benchmark report did not pass")
    for field, expected in (
        ("iterations", _M2607_BENCHMARK_ITERATIONS),
        ("budgetsNs", {"mean": _M2607_MEAN_BUDGET_NS, "p95": _M2607_P95_BUDGET_NS}),
    ):
        if benchmark_report.get(field) != expected:
            raise ReleaseArtifactError(f"M26-07 benchmark report has an unexpected {field}")
    samples = _sequence(benchmark_report.get("samplesNs"), "M26-07 benchmark samples")
    if len(samples) != _M2607_BENCHMARK_ITERATIONS or any(
        type(sample) is not int or sample < 0 for sample in samples
    ):
        raise ReleaseArtifactError("M26-07 benchmark samples are invalid")
    mean = benchmark_report.get("meanNs")
    p95 = benchmark_report.get("p95Ns")
    if (
        type(mean) is not int
        or type(p95) is not int
        or mean < 0
        or p95 < 0
        or mean > _M2607_MEAN_BUDGET_NS
        or p95 > _M2607_P95_BUDGET_NS
    ):
        raise ReleaseArtifactError("M26-07 benchmark report exceeds timing budgets")


def _verify_m2607_package(package_report: Mapping[str, object]) -> None:
    if package_report.get("moduleId") != _M2607_MODULE_ID:
        raise ReleaseArtifactError("M26-07 package report has the wrong module identity")
    if package_report.get("contractVersion") != "0.1.0-provisional":
        raise ReleaseArtifactError("M26-07 package report has the wrong contract version")
    for label in ("wheel", "sdist"):
        artifact = _mapping(package_report.get(label), f"M26-07 {label} package")
        filename = artifact.get("filename")
        digest = artifact.get("sha256")
        size = artifact.get("sizeBytes")
        members = artifact.get("memberCount")
        if (
            not isinstance(filename, str)
            or not filename
            or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or type(size) is not int
            or size <= 0
            or type(members) is not int
            or members <= 0
        ):
            raise ReleaseArtifactError(f"M26-07 {label} package evidence is incomplete")
    required_members = _sequence(
        _mapping(package_report.get("wheel"), "M26-07 wheel package").get(
            "requiredRuntimeMembers"
        ),
        "M26-07 required runtime members",
    )
    if not required_members or any(
        not isinstance(member, str) or not member for member in required_members
    ):
        raise ReleaseArtifactError("M26-07 required runtime member closure is incomplete")
    if package_report.get("isolatedImportPassed") is not True:
        raise ReleaseArtifactError("M26-07 isolated import evidence did not pass")


def verify_m2607_evidence(evaluation: Path, benchmark: Path, package: Path | None = None) -> None:
    """Verify M26-07 scenario, benchmark, and optional package evidence."""

    _verify_m2607_evaluation(_load_json_evidence(evaluation, "M26-07 evaluation report"))
    _verify_m2607_benchmark(_load_json_evidence(benchmark, "M26-07 benchmark report"))
    if package is not None:
        _verify_m2607_package(_load_json_evidence(package, "M26-07 package report"))


def _verify_reproducible_cyclonedx_header(
    document: Mapping[str, object],
) -> Mapping[str, object]:
    if document.get("bomFormat") != "CycloneDX":
        raise ReleaseArtifactError("runtime SBOM is not CycloneDX")
    if document.get("specVersion") != "1.6":
        raise ReleaseArtifactError("runtime SBOM uses an unexpected specification version")
    if "serialNumber" in document:
        raise ReleaseArtifactError("runtime SBOM contains a non-reproducible serial number")
    metadata = _mapping(document.get("metadata"), "metadata")
    if "timestamp" in metadata:
        raise ReleaseArtifactError("runtime SBOM contains a non-reproducible timestamp")
    return metadata


def verify_runtime_sbom(sbom: Path, wheel: Path) -> RuntimeSbomSummary:
    """Verify that *sbom* is a runtime-only CycloneDX BOM rooted at *wheel*."""

    identity = wheel_identity(wheel)
    document = _load_sbom(sbom)
    metadata = _verify_reproducible_cyclonedx_header(document)
    root = _mapping(metadata.get("component"), "root component")
    root_name = root.get("name")
    root_version = root.get("version")
    root_reference = root.get("bom-ref")
    if not isinstance(root_name, str) or not isinstance(root_version, str):
        raise ReleaseArtifactError("runtime SBOM root identity is incomplete")
    if (
        _normalized_distribution_name(root_name) != _normalized_distribution_name(identity.name)
        or root_version != identity.version
    ):
        raise ReleaseArtifactError("runtime SBOM root does not match the candidate wheel")
    if root.get("type") != "application":
        raise ReleaseArtifactError("runtime SBOM root must be an application component")
    if not isinstance(root_reference, str) or not root_reference:
        raise ReleaseArtifactError("runtime SBOM root has no dependency reference")

    dependencies = _sequence(document.get("dependencies"), "dependencies")
    root_edges = sum(
        _mapping(item, "dependency entry").get("ref") == root_reference for item in dependencies
    )
    if root_edges != 1:
        raise ReleaseArtifactError("runtime SBOM dependency graph does not contain one root")

    components = _sequence(document.get("components"), "components")
    component_names: set[str] = set()
    for item in components:
        component = _mapping(item, "component")
        name = component.get("name")
        if not isinstance(name, str) or not name:
            raise ReleaseArtifactError("runtime SBOM contains a component without a name")
        component_names.add(_normalized_distribution_name(name))
    leaked = sorted(component_names & _FORBIDDEN_RUNTIME_COMPONENTS)
    if leaked:
        raise ReleaseArtifactError("runtime SBOM contains development-only components")

    return RuntimeSbomSummary(
        root_name=root_name,
        root_version=root_version,
        component_count=len(components),
    )


def _installed_console_script() -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    executable = Path(sys.executable).with_name(f"{_CONSOLE_SCRIPT}{suffix}")
    if not executable.is_file():
        raise ReleaseArtifactError("installed wheel has no console script")
    return executable


def _installed_distribution(
    identity: WheelIdentity,
) -> tuple[importlib.metadata.Distribution, Path]:
    try:
        distribution = importlib.metadata.distribution(identity.name)
    except importlib.metadata.PackageNotFoundError as error:
        raise ReleaseArtifactError("candidate distribution is not installed") from error

    installed_name = distribution.metadata.get("Name")
    if not isinstance(installed_name, str):
        raise ReleaseArtifactError("installed distribution identity is incomplete")
    if (
        _normalized_distribution_name(installed_name)
        != _normalized_distribution_name(identity.name)
        or distribution.version != identity.version
    ):
        raise ReleaseArtifactError("installed distribution does not match the candidate wheel")

    environment = Path(sys.prefix).resolve()
    distribution_root = Path(str(distribution.locate_file(""))).resolve()
    if not distribution_root.is_relative_to(environment):
        raise ReleaseArtifactError("candidate distribution is outside the clean environment")
    return distribution, environment


def _verify_direct_wheel_install(
    distribution: importlib.metadata.Distribution,
    wheel: Path,
) -> None:
    direct_url_text = distribution.read_text("direct_url.json")
    if direct_url_text is None:
        raise ReleaseArtifactError("candidate distribution has no direct wheel provenance")
    try:
        direct_url: object = json.loads(direct_url_text)
    except json.JSONDecodeError as error:
        raise ReleaseArtifactError("candidate distribution provenance is malformed") from error
    direct_url_mapping = _mapping(direct_url, "installed provenance")
    source_url = direct_url_mapping.get("url")
    if not isinstance(source_url, str) or "dir_info" in direct_url_mapping:
        raise ReleaseArtifactError("candidate distribution was not installed from a wheel")
    parsed_url = urlsplit(source_url)
    if (
        parsed_url.scheme != "file"
        or parsed_url.netloc.casefold() not in {"", "localhost"}
        or parsed_url.query
        or parsed_url.fragment
    ):
        raise ReleaseArtifactError("candidate wheel provenance is not one local file")
    source_path = Path(url2pathname(parsed_url.path)).resolve()
    if source_path != wheel.resolve():
        raise ReleaseArtifactError("installed distribution came from a different wheel")


def _verify_installed_files(
    distribution: importlib.metadata.Distribution,
    environment: Path,
    wheel: Path,
) -> None:
    try:
        with ZipFile(wheel) as archive:
            for member in archive.infolist():
                wheel_path = PurePosixPath(member.filename)
                if member.is_dir():
                    continue
                if wheel_path.is_absolute() or ".." in wheel_path.parts:
                    raise ReleaseArtifactError("candidate wheel contains an unsafe member path")
                if member.filename.endswith(".dist-info/RECORD"):
                    continue
                installed_path = Path(
                    str(distribution.locate_file(Path(*wheel_path.parts)))
                ).resolve()
                if not installed_path.is_relative_to(environment):
                    raise ReleaseArtifactError("candidate wheel member escaped the environment")
                try:
                    installed_digest = _sha256(installed_path)
                except OSError as error:
                    raise ReleaseArtifactError("candidate wheel member is not installed") from error
                archive_digest = hashlib.sha256(archive.read(member)).hexdigest()
                if installed_digest != archive_digest:
                    raise ReleaseArtifactError("installed file does not match the candidate wheel")
    except (BadZipFile, OSError) as error:
        raise ReleaseArtifactError("candidate wheel members cannot be verified") from error


def _verify_package_import(identity: WheelIdentity, environment: Path) -> None:
    package = importlib.import_module(_PACKAGE_NAME)
    package_path_value = getattr(package, "__file__", None)
    if not isinstance(package_path_value, str):
        raise ReleaseArtifactError("installed package has no import origin")
    if not Path(package_path_value).resolve().is_relative_to(environment):
        raise ReleaseArtifactError("package import resolved outside the clean environment")
    if getattr(package, "__version__", None) != identity.version:
        raise ReleaseArtifactError("package version does not match wheel metadata")


def _verify_console_script() -> None:
    entry_points = tuple(
        entry_point
        for entry_point in importlib.metadata.entry_points(group="console_scripts")
        if entry_point.name == _CONSOLE_SCRIPT
    )
    if len(entry_points) != 1 or entry_points[0].value != _CONSOLE_ENTRY_POINT:
        raise ReleaseArtifactError("candidate wheel has an unexpected console entry point")
    executable = str(_installed_console_script())
    for arguments, expected_schema_id in _CLI_SCHEMA_SMOKE_TESTS:
        completed = subprocess.run(  # noqa: S603 - path is from this trusted interpreter.
            [executable, *arguments],
            cwd=Path.cwd(),
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if completed.returncode != 0:
            raise ReleaseArtifactError("installed console-script smoke test failed")
        try:
            schema: object = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise ReleaseArtifactError(
                "installed console script emitted invalid schema JSON"
            ) from error
        exported = _mapping(schema, "exported schema")
        if exported.get("$schema") != _SCHEMA_URI:
            raise ReleaseArtifactError("installed console script emitted the wrong schema dialect")
        if exported.get("$id") != expected_schema_id:
            raise ReleaseArtifactError("installed console script emitted the wrong contract")


def verify_installed_wheel(wheel: Path) -> WheelIdentity:
    """Prove this interpreter imports a non-editable install matching *wheel*."""

    identity = wheel_identity(wheel)
    distribution, environment = _installed_distribution(identity)
    _verify_direct_wheel_install(distribution, wheel)
    _verify_installed_files(distribution, environment, wheel)
    _verify_package_import(identity, environment)
    _verify_console_script()
    return identity


def _write_install_report(path: Path, identity: WheelIdentity) -> None:
    report = {
        "distribution": identity.name,
        "schema_dialect": _SCHEMA_URI,
        "version": identity.version,
        "verified_cli_schema_routes": [
            {
                "arguments": list(arguments),
                "schema_id": schema_id,
            }
            for arguments, schema_id in _CLI_SCHEMA_SMOKE_TESTS
        ],
        "wheel": {"filename": identity.filename, "sha256": identity.sha256},
    }
    path.write_text(
        json.dumps(report, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _verify_expected_tag(identity: WheelIdentity, expected_tag: str | None) -> None:
    if expected_tag is not None and expected_tag != f"v{identity.version}":
        raise ReleaseArtifactError("release tag does not match candidate wheel version")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    installed = commands.add_parser(
        "installed-wheel", help="verify the wheel installed in this interpreter"
    )
    installed.add_argument("wheel", type=Path)
    installed.add_argument("--expected-tag")
    installed.add_argument("--report", type=Path)
    runtime_sbom = commands.add_parser(
        "runtime-sbom", help="verify a runtime SBOM against its candidate wheel"
    )
    runtime_sbom.add_argument("sbom", type=Path)
    runtime_sbom.add_argument("wheel", type=Path)
    m0403_evidence = commands.add_parser(
        "m04-03-evidence", help="verify M04-03 evaluation and benchmark evidence"
    )
    m0403_evidence.add_argument("evaluation", type=Path)
    m0403_evidence.add_argument("benchmark", type=Path)
    m0404_evidence = commands.add_parser(
        "m04-04-evidence", help="verify M04-04 evaluation and benchmark evidence"
    )
    m0404_evidence.add_argument("evaluation", type=Path)
    m0404_evidence.add_argument("benchmark", type=Path)
    m1904_evidence = commands.add_parser(
        "m19-04-evidence", help="verify M19-04 evaluation and benchmark evidence"
    )
    m1904_evidence.add_argument("evaluation", type=Path)
    m1904_evidence.add_argument("benchmark", type=Path)
    m2604_evidence = commands.add_parser(
        "m26-04-evidence", help="verify M26-04 evaluation and benchmark evidence"
    )
    m2604_evidence.add_argument("evaluation", type=Path)
    m2604_evidence.add_argument("benchmark", type=Path)
    m2607_evidence = commands.add_parser(
        "m26-07-evidence", help="verify M26-07 evaluation and benchmark evidence"
    )
    m2607_evidence.add_argument("evaluation", type=Path)
    m2607_evidence.add_argument("benchmark", type=Path)
    m2607_evidence.add_argument("package", type=Path)
    return parser


def main() -> int:
    """Run release-artifact verification without exposing artifact contents on failure."""

    arguments = _parser().parse_args()
    try:
        if arguments.command == "installed-wheel":
            identity = verify_installed_wheel(arguments.wheel)
            _verify_expected_tag(identity, arguments.expected_tag)
            if arguments.report is not None:
                _write_install_report(arguments.report, identity)
        elif arguments.command == "runtime-sbom":
            verify_runtime_sbom(arguments.sbom, arguments.wheel)
        elif arguments.command == "m04-03-evidence":
            verify_m0403_evidence(arguments.evaluation, arguments.benchmark)
        elif arguments.command == "m19-04-evidence":
            verify_m1904_evidence(arguments.evaluation, arguments.benchmark)
        elif arguments.command == "m26-04-evidence":
            verify_m2604_evidence(arguments.evaluation, arguments.benchmark)
        elif arguments.command == "m26-07-evidence":
            verify_m2607_evidence(arguments.evaluation, arguments.benchmark, arguments.package)
        else:
            verify_m0404_evidence(arguments.evaluation, arguments.benchmark)
    except ReleaseArtifactError as error:
        sys.stderr.write(f"release artifact verification failed: {error}\n")
        return 1
    sys.stdout.write("release artifact verification passed\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
