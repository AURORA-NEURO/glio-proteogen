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
from statistics import fmean, median
from typing import TYPE_CHECKING, cast
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
_M0405_MODULE_ID = "GLIO-PROTEOGEN-M04-05"
_M0405_OPERATION = "detect_proteoform_artifacts"
_M0405_CASE_COUNT = 15
_M0405_BENCHMARK_ITERATIONS = 25
_M0405_BENCHMARK_WARMUPS = 1
_M0405_MEAN_BUDGET_NS = 2_000_000_000
_M0405_P95_BUDGET_NS = 3_000_000_000
_M0405_BENCHMARK_SHAPE = {
    "target_count": 64,
    "event_count": 448,
    "posterior_count": 448,
}
_M0405_SEEDED_SENSITIVITY_FLOOR_PPM = 900_000
_M0405_FALSE_EXCLUSION_CEILING_PPM = 50_000
_PPM_SCALE = 1_000_000
_M0405_COVERAGE_DISPOSITION = "non_calibrated_scores_with_typed_narrowing_or_abstention"
_M0405_CONTRACT_VERSION = "1.0.0"
_M0405_BENCHMARK_WORKLOAD = (
    "genuine M04-04 result plus the exact installed maximum aggregate ledger"
)
_M0405_TIMED_BOUNDARY = "detect_proteoform_artifacts only"
_CANONICAL_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
_M0501_MODULE_ID = "GLIO-PROTEOGEN-M05-01"
_M0501_CASE_COUNT = 40
_M0501_GROUP_COUNT = 8
_M0501_CASES_PER_GROUP = 5
_M0501_BENCHMARK_ITERATIONS = 25
_M0501_BENCHMARK_WARMUPS = 1
_M0501_MEAN_BUDGET_NS = 2_000_000_000
_M0501_P95_BUDGET_NS = 3_000_000_000
_M0501_MAX_REQUEST_BYTES = 4 * 1024 * 1024
_M0501_BENCHMARK_SHAPE = {
    "reference_bundle_count": 32,
    "approved_version_count": 16,
    "vocabulary_count": 16,
    "vocabulary_term_count": 12,
    "unit_policy_count": 6,
    "metadata_field_count": 8,
    "compatibility_rule_count": 32,
}
_M0502_MODULE_ID = "GLIO-PROTEOGEN-M05-02"
_M0502_CASE_COUNT = 70
_M0502_GROUP_COUNTS = {
    "identity_and_lineage": 9,
    "artifact_anomaly_detection": 9,
    "safe_failure_and_support": 9,
    "authorization_firewall": 9,
    "strict_contract": 9,
    "dag_invariants": 9,
    "replay_and_privacy": 8,
    "uncertainty_recovery_interfaces": 8,
}
_M0502_BENCHMARK_ITERATIONS = 25
_M0502_BENCHMARK_WARMUPS = 1
_M0502_MEAN_BUDGET_NS = 400_000_000
_M0502_P95_BUDGET_NS = 750_000_000
_M0502_MAX_REQUEST_BYTES = 4 * 1024 * 1024
_M0502_BENCHMARK_WORKLOAD = "maximum_reconciled_five_role_identity_lineage_graph"
_M0502_TIMED_BOUNDARY = "reconcile_ptm_localization_identity_lineage_only"
_M0502_BENCHMARK_SHAPE = {
    "physical_entity_kind_count": 7,
    "artifact_role_count": 5,
    "artifact_claim_count": 5,
    "derivation_count": 1,
    "derivation_source_count": 4,
    "finding_count": 0,
}
_M0503_MODULE_ID = "GLIO-PROTEOGEN-M05-03"
_M0503_CASE_COUNT = 72
_M0503_BENCHMARK_ITERATIONS = 25
_M0503_BENCHMARK_WARMUPS = 1
_M0503_MEAN_BUDGET_NS = 500_000_000
_M0503_P95_BUDGET_NS = 750_000_000
_M0503_MAX_REQUEST_BYTES = 4 * 1024 * 1024
_M0503_BENCHMARK_WORKLOAD = "genuine_four_modest_canonical_raw_manifest_documents"
_M0503_TIMED_BOUNDARY = "ingest_ptm_localization_raw_inputs_only"
_M0503_BENCHMARK_SHAPE = {
    "input_artifact_count": 4,
    "document_count": 4,
    "validated_input_count": 4,
    "diagnostic_count": 0,
    "evidence_count": 20,
    "limitation_count": 3,
}
_M0503_FIXTURE_DIGEST = "sha256:903ba155ed64680d527991d558ebc4ee96e4e11342e7ace6ab309f461222a796"
_M0503_GROUP_COUNTS = (7, 9, 8, 8, 8, 7, 7, 18)
_M0503_BENCHMARK_REQUEST_BYTES = 83_113
_M0503_BENCHMARK_RESULT_BYTES = 109_985
_M0503_BENCHMARK_REQUEST_DIGEST = (
    "sha256:55d852052b12e741cafd94a206c57b43d5e4c67601b41673d8bb75d467bd679c"
)
_M0503_BENCHMARK_RESULT_DIGEST = (
    "sha256:06b5f27a7cafa4e89d50579cc2600b14dc1c9d81caf6021cef872dd38460d93b"
)
_M0504_MODULE_ID = "GLIO-PROTEOGEN-M05-04"
_M0504_CASE_COUNT = 72
_M0504_BENCHMARK_ITERATIONS = 25
_M0504_BENCHMARK_WARMUPS = 1
_M0504_MEAN_BUDGET_NS = 500_000_000
_M0504_P95_BUDGET_NS = 750_000_000
_M0504_MAX_REQUEST_BYTES = 4 * 1024 * 1024
_M0504_BENCHMARK_WORKLOAD = "genuine_maximum_supported_quality_metadata_shape"
_M0504_TIMED_BOUNDARY = "compute_ptm_localization_quality_metrics_only"
_M0504_BENCHMARK_SHAPE = {
    "role_count": 4,
    "profile_count": 32,
    "threshold_count": 256,
    "fact_count": 4,
    "metric_count": 32,
    "evidence_count": 45,
    "limitation_count": 3,
}
_M0504_FIXTURE_DIGEST = "sha256:51937dd64eb9b7458d20ec66c5827f903abc0e02547c8f7d181e9c3c38002889"
_M0504_GROUP_COUNTS = (8, 9, 9, 9, 8, 8, 8, 13)
_M0504_BENCHMARK_REQUEST_BYTES = 176_995
_M0504_BENCHMARK_RESULT_BYTES = 243_460
_M0504_BENCHMARK_REQUEST_DIGEST = (
    "sha256:c8001d0d9593f6046a7787ba2fe00ee26f29973d45a34c91d33afad3dfd67410"
)
_M0504_BENCHMARK_RESULT_DIGEST = (
    "sha256:e1e87f3915d450910fe2d3113f5ec94727540e4a29b8f4d595ab300bf1b5f6f0"
)
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
    (
        ("proteoform-artifacts", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M04-05:1.0.0:request",
    ),
    (
        ("m05-01-export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M05-01:1.0.0:request",
    ),
    (
        ("m05-02-export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M05-02:1.0.0:request",
    ),
    (
        ("ptm-localization-raw", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M05-03:1.0.0:request",
    ),
    (
        ("ptm-localization-quality", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M05-04:1.0.0:request",
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


def _require_positive_integer(document: Mapping[str, object], field: str, label: str) -> int:
    value = document.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ReleaseArtifactError(f"{label} has an invalid {field}")
    return value


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


def _verify_m0405_checks(checked: Sequence[Mapping[str, object]]) -> None:
    if any(check.get("passed") is not True for check in checked):
        raise ReleaseArtifactError("M04-05 evaluation report contains a failed check")
    scenario_names = tuple(
        name
        for check in checked
        if isinstance((name := check.get("name")), str) and name.startswith("scenario.")
    )
    replay_names = tuple(
        name
        for check in checked
        if isinstance((name := check.get("name")), str) and name.startswith("replay.")
    )
    for kind, names in (("scenario", scenario_names), ("replay", replay_names)):
        if len(names) != _M0405_CASE_COUNT or len(set(names)) != len(names):
            raise ReleaseArtifactError(f"M04-05 evaluation report lacks exact {kind} closure")
    if {name.removeprefix("scenario.") for name in scenario_names} != {
        name.removeprefix("replay.") for name in replay_names
    }:
        raise ReleaseArtifactError("M04-05 evaluation report replays a different corpus")
    required_oracle = tuple(
        check
        for check in checked
        if check.get("name") == "acceptance.non_calibrated_narrow_or_abstain"
    )
    if len(required_oracle) != 1 or required_oracle[0].get("passed") is not True:
        raise ReleaseArtifactError("M04-05 evaluation report lacks its narrowed-support oracle")


def _verify_m0405_acceptance_metrics(evaluation_report: Mapping[str, object]) -> None:
    sensitivity = evaluation_report.get("seeded_sensitivity_ppm")
    if (
        type(sensitivity) is not int
        or sensitivity < _M0405_SEEDED_SENSITIVITY_FLOOR_PPM
        or sensitivity > _PPM_SCALE
    ):
        raise ReleaseArtifactError("M04-05 evaluation report misses its sensitivity floor")
    false_exclusion = evaluation_report.get("false_exclusion_ppm")
    if (
        type(false_exclusion) is not int
        or false_exclusion < 0
        or false_exclusion > _M0405_FALSE_EXCLUSION_CEILING_PPM
    ):
        raise ReleaseArtifactError("M04-05 evaluation report exceeds its false-exclusion ceiling")
    if evaluation_report.get("nominal_coverage_ppm", object()) is not None:
        raise ReleaseArtifactError("M04-05 evaluation report claims unsupported nominal coverage")
    if evaluation_report.get("coverage_disposition") != _M0405_COVERAGE_DISPOSITION:
        raise ReleaseArtifactError("M04-05 evaluation report has the wrong coverage disposition")


def _verify_m0405_evaluation(evaluation_report: Mapping[str, object]) -> None:
    label = "M04-05 evaluation report"
    if evaluation_report.get("module_id") != _M0405_MODULE_ID:
        raise ReleaseArtifactError(f"{label} has the wrong module identity")
    if evaluation_report.get("operation") != _M0405_OPERATION:
        raise ReleaseArtifactError(f"{label} has the wrong operation")
    if evaluation_report.get("passed") is not True:
        raise ReleaseArtifactError(f"{label} did not pass")
    for field in ("declared_case_count", "executed_case_count"):
        _require_exact_integer(evaluation_report, field, _M0405_CASE_COUNT, label)
    for field in ("missing_case_ids", "extra_case_ids", "duplicated_case_ids"):
        _require_empty_array(evaluation_report, field, label)
    checks = _sequence(evaluation_report.get("checks"), "M04-05 evaluation checks")
    checked = tuple(_mapping(check, "M04-05 evaluation check") for check in checks)
    _verify_m0405_checks(checked)
    _verify_m0405_acceptance_metrics(evaluation_report)


def _verify_m0405_benchmark_identity(benchmark_report: Mapping[str, object]) -> None:
    label = "M04-05 benchmark report"
    if benchmark_report.get("module_id") != _M0405_MODULE_ID:
        raise ReleaseArtifactError(f"{label} has the wrong module identity")
    if benchmark_report.get("passed") is not True:
        raise ReleaseArtifactError(f"{label} did not pass")
    for field, expected_text in (
        ("contract_version", _M0405_CONTRACT_VERSION),
        ("workload", _M0405_BENCHMARK_WORKLOAD),
        ("timed_boundary", _M0405_TIMED_BOUNDARY),
    ):
        if benchmark_report.get(field) != expected_text:
            raise ReleaseArtifactError(f"{label} has an unexpected {field}")
    for field in ("request_digest", "result_digest"):
        value = benchmark_report.get(field)
        if not isinstance(value, str) or _CANONICAL_SHA256.fullmatch(value) is None:
            raise ReleaseArtifactError(f"{label} has an invalid {field}")
    exact_fields = {
        "iterations": _M0405_BENCHMARK_ITERATIONS,
        "warmup_count": _M0405_BENCHMARK_WARMUPS,
        "mean_budget_ns": _M0405_MEAN_BUDGET_NS,
        "p95_budget_ns": _M0405_P95_BUDGET_NS,
        **_M0405_BENCHMARK_SHAPE,
    }
    for field, expected_integer in exact_fields.items():
        _require_exact_integer(benchmark_report, field, expected_integer, label)


def _verify_m0405_benchmark_timing(benchmark_report: Mapping[str, object]) -> None:
    mean = benchmark_report.get("mean_ns")
    p50 = benchmark_report.get("p50_ns")
    p95 = benchmark_report.get("p95_ns")
    maximum = benchmark_report.get("maximum_ns")
    if isinstance(mean, bool) or not isinstance(mean, (int, float)):
        raise ReleaseArtifactError("M04-05 benchmark report has an invalid mean")
    if isinstance(p50, bool) or not isinstance(p50, (int, float)):
        raise ReleaseArtifactError("M04-05 benchmark report has an invalid p50")
    if isinstance(p95, bool) or not isinstance(p95, int):
        raise ReleaseArtifactError("M04-05 benchmark report has an invalid p95")
    if isinstance(maximum, bool) or not isinstance(maximum, int):
        raise ReleaseArtifactError("M04-05 benchmark report has an invalid maximum")
    if (
        not math.isfinite(mean)
        or not math.isfinite(p50)
        or mean < 0
        or mean > _M0405_MEAN_BUDGET_NS
        or p50 < 0
        or p95 < 0
        or p95 > _M0405_P95_BUDGET_NS
        or maximum < p95
        or maximum < p50
        or maximum < mean
    ):
        raise ReleaseArtifactError("M04-05 benchmark report exceeds its timing budgets")


def _verify_m0405_benchmark(benchmark_report: Mapping[str, object]) -> None:
    _verify_m0405_benchmark_identity(benchmark_report)
    _verify_m0405_benchmark_timing(benchmark_report)


def verify_m0405_evidence(evaluation: Path, benchmark: Path) -> None:
    """Verify M04-05 corpus closure, narrowed uncertainty, and maximum-shape timing."""

    _verify_m0405_evaluation(_load_json_evidence(evaluation, "M04-05 evaluation report"))
    _verify_m0405_benchmark(_load_json_evidence(benchmark, "M04-05 benchmark report"))


def _verify_m0501_evaluation(evaluation_report: Mapping[str, object]) -> None:
    if evaluation_report.get("module_id") != _M0501_MODULE_ID:
        raise ReleaseArtifactError("M05-01 evaluation report has the wrong module identity")
    if evaluation_report.get("contract_version") != "1.0.0":
        raise ReleaseArtifactError("M05-01 evaluation report has the wrong contract version")
    if evaluation_report.get("passed") is not True:
        raise ReleaseArtifactError("M05-01 evaluation report did not pass")
    for field, expected in (
        ("declared_groups", _M0501_GROUP_COUNT),
        ("declared_cases", _M0501_CASE_COUNT),
        ("executed_cases", _M0501_CASE_COUNT),
        ("passed_cases", _M0501_CASE_COUNT),
    ):
        _require_exact_integer(evaluation_report, field, expected, "M05-01 evaluation report")
    _require_empty_array(evaluation_report, "failed_cases", "M05-01 evaluation report")
    counts = _mapping(
        evaluation_report.get("group_case_counts"),
        "M05-01 evaluation group counts",
    )
    if len(counts) != _M0501_GROUP_COUNT or any(
        type(value) is not int or value != _M0501_CASES_PER_GROUP for value in counts.values()
    ):
        raise ReleaseArtifactError("M05-01 evaluation report lacks exact group closure")


def _verify_m0501_benchmark(benchmark_report: Mapping[str, object]) -> None:
    if benchmark_report.get("module_id") != _M0501_MODULE_ID:
        raise ReleaseArtifactError("M05-01 benchmark report has the wrong module identity")
    if benchmark_report.get("contract_version") != "1.0.0":
        raise ReleaseArtifactError("M05-01 benchmark report has the wrong contract version")
    if benchmark_report.get("passed") is not True:
        raise ReleaseArtifactError("M05-01 benchmark report did not pass")
    exact_fields = {
        "iterations": _M0501_BENCHMARK_ITERATIONS,
        "warmup_count": _M0501_BENCHMARK_WARMUPS,
        "mean_budget_ns": _M0501_MEAN_BUDGET_NS,
        "p95_budget_ns": _M0501_P95_BUDGET_NS,
        **_M0501_BENCHMARK_SHAPE,
    }
    for field, expected in exact_fields.items():
        _require_exact_integer(benchmark_report, field, expected, "M05-01 benchmark report")
    request_bytes = _require_positive_integer(
        benchmark_report, "request_bytes", "M05-01 benchmark report"
    )
    _require_positive_integer(benchmark_report, "result_bytes", "M05-01 benchmark report")
    if request_bytes > _M0501_MAX_REQUEST_BYTES:
        raise ReleaseArtifactError("M05-01 maximum request exceeds its installed byte cap")
    mean = benchmark_report.get("mean_ns")
    p95 = benchmark_report.get("p95_ns")
    if isinstance(mean, bool) or not isinstance(mean, (int, float)):
        raise ReleaseArtifactError("M05-01 benchmark report has an invalid mean")
    if isinstance(p95, bool) or not isinstance(p95, int):
        raise ReleaseArtifactError("M05-01 benchmark report has an invalid p95")
    if (
        not math.isfinite(mean)
        or mean < 0
        or mean > _M0501_MEAN_BUDGET_NS
        or p95 < 0
        or p95 > _M0501_P95_BUDGET_NS
    ):
        raise ReleaseArtifactError("M05-01 benchmark report exceeds its timing budgets")


def verify_m0501_evidence(evaluation: Path, benchmark: Path) -> None:
    """Verify exact M05-01 corpus closure, maximum shape, and timing budgets."""

    _verify_m0501_evaluation(_load_json_evidence(evaluation, "M05-01 evaluation report"))
    _verify_m0501_benchmark(_load_json_evidence(benchmark, "M05-01 benchmark report"))


def _verify_m0502_evaluation(evaluation_report: Mapping[str, object]) -> None:
    if evaluation_report.get("module_id") != _M0502_MODULE_ID:
        raise ReleaseArtifactError("M05-02 evaluation report has the wrong module identity")
    if evaluation_report.get("contract_version") != "1.0.0":
        raise ReleaseArtifactError("M05-02 evaluation report has the wrong contract version")
    if evaluation_report.get("passed") is not True:
        raise ReleaseArtifactError("M05-02 evaluation report did not pass")
    for field, expected in (
        ("declared_groups", len(_M0502_GROUP_COUNTS)),
        ("declared_cases", _M0502_CASE_COUNT),
        ("executed_cases", _M0502_CASE_COUNT),
        ("passed_cases", _M0502_CASE_COUNT),
    ):
        _require_exact_integer(evaluation_report, field, expected, "M05-02 evaluation report")
    _require_empty_array(evaluation_report, "failed_cases", "M05-02 evaluation report")
    counts = _mapping(
        evaluation_report.get("group_case_counts"),
        "M05-02 evaluation group counts",
    )
    if dict(counts) != _M0502_GROUP_COUNTS:
        raise ReleaseArtifactError("M05-02 evaluation report lacks exact group closure")


def _verify_m0502_benchmark(  # noqa: C901 - explicit locked evidence matrix.
    benchmark_report: Mapping[str, object],
) -> None:
    if benchmark_report.get("module_id") != _M0502_MODULE_ID:
        raise ReleaseArtifactError("M05-02 benchmark report has the wrong module identity")
    if benchmark_report.get("contract_version") != "1.0.0":
        raise ReleaseArtifactError("M05-02 benchmark report has the wrong contract version")
    if benchmark_report.get("passed") is not True:
        raise ReleaseArtifactError("M05-02 benchmark report did not pass")
    if benchmark_report.get("workload") != _M0502_BENCHMARK_WORKLOAD:
        raise ReleaseArtifactError("M05-02 benchmark report has the wrong workload")
    if benchmark_report.get("timed_boundary") != _M0502_TIMED_BOUNDARY:
        raise ReleaseArtifactError("M05-02 benchmark report has the wrong timed boundary")
    exact_fields = {
        "iterations": _M0502_BENCHMARK_ITERATIONS,
        "warmup_count": _M0502_BENCHMARK_WARMUPS,
        "mean_budget_ns": _M0502_MEAN_BUDGET_NS,
        "p95_budget_ns": _M0502_P95_BUDGET_NS,
        **_M0502_BENCHMARK_SHAPE,
    }
    for field, expected in exact_fields.items():
        _require_exact_integer(benchmark_report, field, expected, "M05-02 benchmark report")
    request_bytes = _require_positive_integer(
        benchmark_report, "request_bytes", "M05-02 benchmark report"
    )
    _require_positive_integer(benchmark_report, "result_bytes", "M05-02 benchmark report")
    if request_bytes > _M0502_MAX_REQUEST_BYTES:
        raise ReleaseArtifactError("M05-02 benchmark request exceeds its installed byte cap")
    for field in ("request_digest", "result_digest"):
        value = benchmark_report.get(field)
        if not isinstance(value, str) or _CANONICAL_SHA256.fullmatch(value) is None:
            raise ReleaseArtifactError(f"M05-02 benchmark report has an invalid {field}")
    mean = benchmark_report.get("mean_ns")
    p50 = benchmark_report.get("p50_ns")
    p95 = benchmark_report.get("p95_ns")
    maximum = benchmark_report.get("maximum_ns")
    if (
        isinstance(mean, bool)
        or not isinstance(mean, (int, float))
        or isinstance(p50, bool)
        or not isinstance(p50, (int, float))
        or isinstance(p95, bool)
        or not isinstance(p95, int)
        or isinstance(maximum, bool)
        or not isinstance(maximum, int)
        or not math.isfinite(mean)
        or not math.isfinite(p50)
        or mean < 0
        or mean > _M0502_MEAN_BUDGET_NS
        or p50 < 0
        or p95 < 0
        or p95 > _M0502_P95_BUDGET_NS
        or maximum < p50
        or maximum < p95
        or maximum < mean
    ):
        raise ReleaseArtifactError("M05-02 benchmark report exceeds its timing budgets")


def verify_m0502_evidence(evaluation: Path, benchmark: Path) -> None:
    """Verify M05-02 locked-corpus closure and representative timing evidence."""

    _verify_m0502_evaluation(_load_json_evidence(evaluation, "M05-02 evaluation report"))
    _verify_m0502_benchmark(_load_json_evidence(benchmark, "M05-02 benchmark report"))


def _m0503_fixture_case_ids(fixture: Path) -> tuple[str, ...]:
    try:
        raw = fixture.read_bytes()
        payload: object = json.loads(raw)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as error:
        raise ReleaseArtifactError("M05-03 fixture is not valid UTF-8 JSON") from error
    digest = f"sha256:{hashlib.sha256(raw).hexdigest()}"
    if digest != _M0503_FIXTURE_DIGEST:
        raise ReleaseArtifactError("M05-03 fixture digest does not match the locked corpus")
    document = _mapping(payload, "M05-03 fixture")
    if (
        document.get("module_id") != _M0503_MODULE_ID
        or document.get("schema_version") != "1.0.0"
        or document.get("expected_group_count") != len(_M0503_GROUP_COUNTS)
        or document.get("expected_total_case_count") != _M0503_CASE_COUNT
        or tuple(_sequence(document.get("expected_case_allocation"), "M05-03 allocation"))
        != _M0503_GROUP_COUNTS
    ):
        raise ReleaseArtifactError("M05-03 fixture has the wrong locked corpus identity")
    groups = _sequence(document.get("scenario_groups"), "M05-03 scenario groups")
    if len(groups) != len(_M0503_GROUP_COUNTS):
        raise ReleaseArtifactError("M05-03 fixture has the wrong group count")
    case_ids: list[str] = []
    for index, group_value in enumerate(groups):
        group = _mapping(group_value, "M05-03 scenario group")
        cases = _sequence(group.get("case_ids"), "M05-03 group case IDs")
        expectations = _mapping(group.get("case_expectations"), "M05-03 case expectations")
        expected_count = _M0503_GROUP_COUNTS[index]
        if (
            group.get("expected_case_count") != expected_count
            or len(cases) != expected_count
            or any(type(case_id) is not str or not case_id for case_id in cases)
            or set(cases) != set(expectations)
        ):
            raise ReleaseArtifactError("M05-03 fixture group closure is invalid")
        case_ids.extend(cast("list[str]", cases))
    if len(case_ids) != _M0503_CASE_COUNT or len(set(case_ids)) != len(case_ids):
        raise ReleaseArtifactError("M05-03 fixture case identifiers are not exact and unique")
    return tuple(case_ids)


def _verify_m0503_evaluation(
    evaluation_report: Mapping[str, object],
    fixture_case_ids: tuple[str, ...],
) -> None:
    if evaluation_report.get("module_id") != _M0503_MODULE_ID:
        raise ReleaseArtifactError("M05-03 evaluation report has the wrong module identity")
    if evaluation_report.get("phase") != "locked_executable_corpus":
        raise ReleaseArtifactError("M05-03 evaluation report has the wrong locked phase")
    if evaluation_report.get("fixture_digest") != _M0503_FIXTURE_DIGEST:
        raise ReleaseArtifactError("M05-03 evaluation report is not bound to the locked fixture")
    if evaluation_report.get("passed") is not True:
        raise ReleaseArtifactError("M05-03 evaluation report did not pass")
    for field in ("declared_case_count", "executed_case_count"):
        _require_exact_integer(
            evaluation_report,
            field,
            _M0503_CASE_COUNT,
            "M05-03 evaluation report",
        )
    for field in ("missing_case_ids", "extra_case_ids", "duplicated_case_ids"):
        _require_empty_array(evaluation_report, field, "M05-03 evaluation report")
    checks = _sequence(evaluation_report.get("checks"), "M05-03 evaluation checks")
    checked = tuple(_mapping(check, "M05-03 evaluation check") for check in checks)
    if any(
        set(check) != {"name", "passed", "detail"}
        or type(check.get("name")) is not str
        or check.get("passed") is not True
        or type(check.get("detail")) is not str
        or not check.get("detail")
        for check in checked
    ):
        raise ReleaseArtifactError("M05-03 evaluation report contains a malformed or failed check")
    names = tuple(cast("str", check["name"]) for check in checked)
    expected_names = (
        "corpus.inventory",
        *(f"scenario.{case_id}" for case_id in fixture_case_ids),
        "corpus.executable_coverage",
    )
    if names != expected_names or len(set(names)) != len(names):
        raise ReleaseArtifactError("M05-03 evaluation report lacks exact fixture scenario closure")


def _verify_m0503_benchmark(  # noqa: C901 - explicit locked evidence matrix.
    benchmark_report: Mapping[str, object],
) -> None:
    if benchmark_report.get("module_id") != _M0503_MODULE_ID:
        raise ReleaseArtifactError("M05-03 benchmark report has the wrong module identity")
    if benchmark_report.get("contract_version") != "1.0.0":
        raise ReleaseArtifactError("M05-03 benchmark report has the wrong contract version")
    if benchmark_report.get("passed") is not True:
        raise ReleaseArtifactError("M05-03 benchmark report did not pass")
    if benchmark_report.get("workload") != _M0503_BENCHMARK_WORKLOAD:
        raise ReleaseArtifactError("M05-03 benchmark report has the wrong workload")
    if benchmark_report.get("timed_boundary") != _M0503_TIMED_BOUNDARY:
        raise ReleaseArtifactError("M05-03 benchmark report has the wrong timed boundary")
    exact_fields = {
        "iterations": _M0503_BENCHMARK_ITERATIONS,
        "warmup_count": _M0503_BENCHMARK_WARMUPS,
        "mean_budget_ns": _M0503_MEAN_BUDGET_NS,
        "p95_budget_ns": _M0503_P95_BUDGET_NS,
        **_M0503_BENCHMARK_SHAPE,
    }
    for field, expected in exact_fields.items():
        _require_exact_integer(benchmark_report, field, expected, "M05-03 benchmark report")
    _require_exact_integer(
        benchmark_report,
        "request_bytes",
        _M0503_BENCHMARK_REQUEST_BYTES,
        "M05-03 benchmark report",
    )
    _require_exact_integer(
        benchmark_report,
        "result_bytes",
        _M0503_BENCHMARK_RESULT_BYTES,
        "M05-03 benchmark report",
    )
    if benchmark_report.get("request_digest") != _M0503_BENCHMARK_REQUEST_DIGEST:
        raise ReleaseArtifactError("M05-03 benchmark report has the wrong request digest")
    if benchmark_report.get("result_digest") != _M0503_BENCHMARK_RESULT_DIGEST:
        raise ReleaseArtifactError("M05-03 benchmark report has the wrong result digest")
    samples_value = _sequence(benchmark_report.get("samples_ns"), "M05-03 timing samples")
    if len(samples_value) != _M0503_BENCHMARK_ITERATIONS or any(
        type(sample) is not int or sample <= 0 for sample in samples_value
    ):
        raise ReleaseArtifactError("M05-03 benchmark report has invalid timing samples")
    samples = tuple(cast("int", sample) for sample in samples_value)
    ordered = sorted(samples)
    recomputed_mean = fmean(samples)
    recomputed_p50 = median(samples)
    recomputed_p95 = ordered[(95 * len(ordered) - 1) // 100]
    recomputed_maximum = max(samples)
    mean = benchmark_report.get("mean_ns")
    p50 = benchmark_report.get("p50_ns")
    p95 = benchmark_report.get("p95_ns")
    maximum = benchmark_report.get("maximum_ns")
    if (
        isinstance(mean, bool)
        or not isinstance(mean, (int, float))
        or isinstance(p50, bool)
        or not isinstance(p50, (int, float))
        or isinstance(p95, bool)
        or not isinstance(p95, int)
        or isinstance(maximum, bool)
        or not isinstance(maximum, int)
        or not math.isfinite(mean)
        or not math.isfinite(p50)
        or mean != recomputed_mean
        or p50 != recomputed_p50
        or p95 != recomputed_p95
        or maximum != recomputed_maximum
        or mean > _M0503_MEAN_BUDGET_NS
        or p95 > _M0503_P95_BUDGET_NS
    ):
        raise ReleaseArtifactError(
            "M05-03 benchmark report disagrees with its samples or exceeds timing budgets"
        )


def verify_m0503_evidence(evaluation: Path, benchmark: Path, fixture: Path) -> None:
    """Verify M05-03 exact corpus closure and representative timing evidence."""

    fixture_case_ids = _m0503_fixture_case_ids(fixture)
    _verify_m0503_evaluation(
        _load_json_evidence(evaluation, "M05-03 evaluation report"), fixture_case_ids
    )
    _verify_m0503_benchmark(_load_json_evidence(benchmark, "M05-03 benchmark report"))


def _m0504_fixture_case_ids(fixture: Path) -> tuple[str, ...]:
    try:
        raw = fixture.read_bytes()
        payload: object = json.loads(raw)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as error:
        raise ReleaseArtifactError("M05-04 fixture is not valid UTF-8 JSON") from error
    digest = f"sha256:{hashlib.sha256(raw).hexdigest()}"
    if digest != _M0504_FIXTURE_DIGEST:
        raise ReleaseArtifactError("M05-04 fixture digest does not match the locked corpus")
    document = _mapping(payload, "M05-04 fixture")
    if (
        document.get("module_id") != _M0504_MODULE_ID
        or document.get("schema_version") != "1.0.0"
        or document.get("expected_group_count") != len(_M0504_GROUP_COUNTS)
        or document.get("expected_total_case_count") != _M0504_CASE_COUNT
        or tuple(_sequence(document.get("expected_case_allocation"), "M05-04 allocation"))
        != _M0504_GROUP_COUNTS
    ):
        raise ReleaseArtifactError("M05-04 fixture has the wrong locked corpus identity")
    groups = _sequence(document.get("scenario_groups"), "M05-04 scenario groups")
    if len(groups) != len(_M0504_GROUP_COUNTS):
        raise ReleaseArtifactError("M05-04 fixture has the wrong group count")
    case_ids: list[str] = []
    for index, group_value in enumerate(groups):
        group = _mapping(group_value, "M05-04 scenario group")
        cases = _sequence(group.get("case_ids"), "M05-04 group case IDs")
        expectations = _mapping(group.get("case_expectations"), "M05-04 case expectations")
        expected_count = _M0504_GROUP_COUNTS[index]
        if (
            group.get("expected_case_count") != expected_count
            or len(cases) != expected_count
            or any(type(case_id) is not str or not case_id for case_id in cases)
            or set(cases) != set(expectations)
        ):
            raise ReleaseArtifactError("M05-04 fixture group closure is invalid")
        case_ids.extend(cast("list[str]", cases))
    if len(case_ids) != _M0504_CASE_COUNT or len(set(case_ids)) != len(case_ids):
        raise ReleaseArtifactError("M05-04 fixture case identifiers are not exact and unique")
    return tuple(case_ids)


def _verify_m0504_evaluation(
    evaluation_report: Mapping[str, object],
    fixture_case_ids: tuple[str, ...],
) -> None:
    if evaluation_report.get("module_id") != _M0504_MODULE_ID:
        raise ReleaseArtifactError("M05-04 evaluation report has the wrong module identity")
    if evaluation_report.get("phase") != "locked_executable_corpus":
        raise ReleaseArtifactError("M05-04 evaluation report has the wrong locked phase")
    if evaluation_report.get("fixture_digest") != _M0504_FIXTURE_DIGEST:
        raise ReleaseArtifactError("M05-04 evaluation report is not bound to the locked fixture")
    if evaluation_report.get("passed") is not True:
        raise ReleaseArtifactError("M05-04 evaluation report did not pass")
    for field in ("declared_case_count", "executed_case_count"):
        _require_exact_integer(
            evaluation_report,
            field,
            _M0504_CASE_COUNT,
            "M05-04 evaluation report",
        )
    for field in ("missing_case_ids", "extra_case_ids", "duplicated_case_ids"):
        _require_empty_array(evaluation_report, field, "M05-04 evaluation report")
    checks = _sequence(evaluation_report.get("checks"), "M05-04 evaluation checks")
    checked = tuple(_mapping(check, "M05-04 evaluation check") for check in checks)
    if any(
        set(check) != {"name", "passed", "detail"}
        or type(check.get("name")) is not str
        or check.get("passed") is not True
        or type(check.get("detail")) is not str
        or not check.get("detail")
        for check in checked
    ):
        raise ReleaseArtifactError("M05-04 evaluation report contains a malformed or failed check")
    names = tuple(cast("str", check["name"]) for check in checked)
    expected_names = (
        "corpus.inventory",
        *(f"scenario.{case_id}" for case_id in fixture_case_ids),
        "corpus.executable_coverage",
    )
    if names != expected_names or len(set(names)) != len(names):
        raise ReleaseArtifactError("M05-04 evaluation report lacks exact fixture scenario closure")


def _verify_m0504_benchmark(  # noqa: C901 - explicit locked evidence matrix.
    benchmark_report: Mapping[str, object],
) -> None:
    if benchmark_report.get("module_id") != _M0504_MODULE_ID:
        raise ReleaseArtifactError("M05-04 benchmark report has the wrong module identity")
    if benchmark_report.get("contract_version") != "1.0.0":
        raise ReleaseArtifactError("M05-04 benchmark report has the wrong contract version")
    if benchmark_report.get("passed") is not True:
        raise ReleaseArtifactError("M05-04 benchmark report did not pass")
    if benchmark_report.get("workload") != _M0504_BENCHMARK_WORKLOAD:
        raise ReleaseArtifactError("M05-04 benchmark report has the wrong workload")
    if benchmark_report.get("timed_boundary") != _M0504_TIMED_BOUNDARY:
        raise ReleaseArtifactError("M05-04 benchmark report has the wrong timed boundary")
    exact_fields = {
        "iterations": _M0504_BENCHMARK_ITERATIONS,
        "warmup_count": _M0504_BENCHMARK_WARMUPS,
        "mean_budget_ns": _M0504_MEAN_BUDGET_NS,
        "p95_budget_ns": _M0504_P95_BUDGET_NS,
        **_M0504_BENCHMARK_SHAPE,
    }
    for field, expected in exact_fields.items():
        _require_exact_integer(benchmark_report, field, expected, "M05-04 benchmark report")
    _require_exact_integer(
        benchmark_report,
        "request_bytes",
        _M0504_BENCHMARK_REQUEST_BYTES,
        "M05-04 benchmark report",
    )
    _require_exact_integer(
        benchmark_report,
        "result_bytes",
        _M0504_BENCHMARK_RESULT_BYTES,
        "M05-04 benchmark report",
    )
    if benchmark_report.get("request_digest") != _M0504_BENCHMARK_REQUEST_DIGEST:
        raise ReleaseArtifactError("M05-04 benchmark report has the wrong request digest")
    if benchmark_report.get("result_digest") != _M0504_BENCHMARK_RESULT_DIGEST:
        raise ReleaseArtifactError("M05-04 benchmark report has the wrong result digest")
    samples_value = _sequence(benchmark_report.get("samples_ns"), "M05-04 timing samples")
    if len(samples_value) != _M0504_BENCHMARK_ITERATIONS or any(
        type(sample) is not int or sample <= 0 for sample in samples_value
    ):
        raise ReleaseArtifactError("M05-04 benchmark report has invalid timing samples")
    samples = tuple(cast("int", sample) for sample in samples_value)
    ordered = sorted(samples)
    recomputed_mean = fmean(samples)
    recomputed_p50 = median(samples)
    recomputed_p95 = ordered[(95 * len(ordered) - 1) // 100]
    recomputed_maximum = max(samples)
    mean = benchmark_report.get("mean_ns")
    p50 = benchmark_report.get("p50_ns")
    p95 = benchmark_report.get("p95_ns")
    maximum = benchmark_report.get("maximum_ns")
    request_bytes = benchmark_report.get("request_bytes")
    if (
        isinstance(mean, bool)
        or not isinstance(mean, (int, float))
        or isinstance(p50, bool)
        or not isinstance(p50, (int, float))
        or isinstance(p95, bool)
        or not isinstance(p95, int)
        or isinstance(maximum, bool)
        or not isinstance(maximum, int)
        or not math.isfinite(mean)
        or not math.isfinite(p50)
        or mean != recomputed_mean
        or p50 != recomputed_p50
        or p95 != recomputed_p95
        or maximum != recomputed_maximum
        or type(request_bytes) is not int
        or request_bytes > _M0504_MAX_REQUEST_BYTES
        or mean > _M0504_MEAN_BUDGET_NS
        or p95 > _M0504_P95_BUDGET_NS
    ):
        raise ReleaseArtifactError(
            "M05-04 benchmark report disagrees with its samples, shape, or timing budgets"
        )


def verify_m0504_evidence(evaluation: Path, benchmark: Path, fixture: Path) -> None:
    """Verify M05-04 exact corpus closure and maximum-shape timing evidence."""

    fixture_case_ids = _m0504_fixture_case_ids(fixture)
    _verify_m0504_evaluation(
        _load_json_evidence(evaluation, "M05-04 evaluation report"), fixture_case_ids
    )
    _verify_m0504_benchmark(_load_json_evidence(benchmark, "M05-04 benchmark report"))


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
    m0405_evidence = commands.add_parser(
        "m04-05-evidence", help="verify M04-05 evaluation and benchmark evidence"
    )
    m0405_evidence.add_argument("evaluation", type=Path)
    m0405_evidence.add_argument("benchmark", type=Path)
    m0501_evidence = commands.add_parser(
        "m05-01-evidence", help="verify M05-01 evaluation and benchmark evidence"
    )
    m0501_evidence.add_argument("evaluation", type=Path)
    m0501_evidence.add_argument("benchmark", type=Path)
    m0502_evidence = commands.add_parser(
        "m05-02-evidence", help="verify M05-02 evaluation and benchmark evidence"
    )
    m0502_evidence.add_argument("evaluation", type=Path)
    m0502_evidence.add_argument("benchmark", type=Path)
    m0503_evidence = commands.add_parser(
        "m05-03-evidence", help="verify M05-03 evaluation and benchmark evidence"
    )
    m0503_evidence.add_argument("evaluation", type=Path)
    m0503_evidence.add_argument("benchmark", type=Path)
    m0503_evidence.add_argument("fixture", type=Path)
    m0504_evidence = commands.add_parser(
        "m05-04-evidence", help="verify M05-04 evaluation and benchmark evidence"
    )
    m0504_evidence.add_argument("evaluation", type=Path)
    m0504_evidence.add_argument("benchmark", type=Path)
    m0504_evidence.add_argument("fixture", type=Path)
    return parser


def main() -> int:  # noqa: C901 - explicit command-to-verifier dispatch.
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
        elif arguments.command == "m04-04-evidence":
            verify_m0404_evidence(arguments.evaluation, arguments.benchmark)
        elif arguments.command == "m04-05-evidence":
            verify_m0405_evidence(arguments.evaluation, arguments.benchmark)
        elif arguments.command == "m05-01-evidence":
            verify_m0501_evidence(arguments.evaluation, arguments.benchmark)
        elif arguments.command == "m05-02-evidence":
            verify_m0502_evidence(arguments.evaluation, arguments.benchmark)
        elif arguments.command == "m05-03-evidence":
            verify_m0503_evidence(arguments.evaluation, arguments.benchmark, arguments.fixture)
        else:
            verify_m0504_evidence(arguments.evaluation, arguments.benchmark, arguments.fixture)
    except ReleaseArtifactError as error:
        sys.stderr.write(f"release artifact verification failed: {error}\n")
        return 1
    sys.stdout.write("release artifact verification passed\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
