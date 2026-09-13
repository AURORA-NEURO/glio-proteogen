"""Focused tests for content-bound, per-module validation receipts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
import tools.verify_module_validation as verifier
from tools.verify_module_validation import (
    BENCHMARK_SMOKE_ITERATIONS,
    MAX_BENCHMARK_OUTPUT_BYTES,
    SCHEMA_VERSION,
    EvidenceConfigurationError,
    ModuleScopeError,
    ModuleValidationError,
    build_report,
    discover_repository,
    normalize_benchmark_report,
    normalize_evaluator_report,
    render_markdown,
    verify,
)

if TYPE_CHECKING:
    from pathlib import Path

EXPECTED_SINGLE_MODULE = 1
EXPECTED_TWO_ARTIFACTS = 2
EXPECTED_THREE_MODULES = 3
EXPECTED_THREE_TESTCASES = 3
EXPECTED_FOUR_MODULES = 4
CLI_USAGE_ERROR = 2
FULL_COVERAGE_PERCENT = 100.0
INVALID_COVERAGE_THRESHOLDS = (-0.1, 100.1, float("nan"), True)
MODULE_ID = "GLIO-PROTEOGEN-M01-01"
SOURCE_ID = "m01_01"


@dataclass(frozen=True)
class _RepositoryOptions:
    request_schema_mutation: dict[str, object] | None = None
    nondeterministic_schema: bool = False
    plugin_has_run: bool = True
    engine_source: str = "VALUE = 1\n"
    evaluator_passed: bool = True
    benchmark_source: str = "BUDGET_SECONDS = 1\n"


def test_static_report_closes_minimal_repository_deterministically(tmp_path: Path) -> None:
    _make_repository(tmp_path)

    first = build_report(tmp_path)
    second = build_report(tmp_path)

    assert first == second
    assert first["summary"]["valid"] is True
    assert first["summary"]["validated_static"] == EXPECTED_SINGLE_MODULE
    assert first["discovery"]["closed_module_count"] == EXPECTED_SINGLE_MODULE
    assert first["modules"][0]["state"] == "validated-static"
    assert first["modules"][0]["contract"]["schema_count"] == EXPECTED_TWO_ARTIFACTS
    assert first["validation_digest"].startswith("sha256:")
    assert render_markdown(first) == render_markdown(second)


def test_explicit_selection_is_canonical_sorted_and_content_bound(tmp_path: Path) -> None:
    _make_repository_with_modules(tmp_path, module_count=EXPECTED_THREE_MODULES)

    first = build_report(tmp_path, module_ids=["m01_03", "M01-01"])
    second = build_report(tmp_path, module_ids=["GLIO-PROTEOGEN-M01-01", "m01_03"])

    assert first["schema_version"] == SCHEMA_VERSION
    assert first["scope"] == second["scope"]
    assert first["scope"]["mode"] == "selection"
    assert first["scope"]["selected_module_ids"] == [
        "GLIO-PROTEOGEN-M01-01",
        "GLIO-PROTEOGEN-M01-03",
    ]
    assert first["scope"]["selected_module_count"] == EXPECTED_TWO_ARTIFACTS
    assert first["discovery"]["closed_module_count"] == EXPECTED_THREE_MODULES
    assert [module["module_id"] for module in first["modules"]] == first["scope"][
        "selected_module_ids"
    ]
    assert first["scope"]["selected_scope_digest"].startswith("sha256:")


def test_round_robin_shards_are_deterministic_disjoint_and_complete(tmp_path: Path) -> None:
    _make_repository_with_modules(tmp_path, module_count=EXPECTED_FOUR_MODULES)

    shard_zero = build_report(tmp_path, shard_index=0, shard_count=EXPECTED_TWO_ARTIFACTS)
    shard_one = build_report(tmp_path, shard_index=1, shard_count=EXPECTED_TWO_ARTIFACTS)
    zero_ids = set(shard_zero["scope"]["selected_module_ids"])
    one_ids = set(shard_one["scope"]["selected_module_ids"])

    assert shard_zero["scope"]["selection_algorithm"] == "sorted-round-robin/1.0.0"
    assert shard_zero["scope"]["mode"] == "shard"
    assert shard_zero["scope"]["selected_module_ids"] == [
        "GLIO-PROTEOGEN-M01-01",
        "GLIO-PROTEOGEN-M01-03",
    ]
    assert shard_one["scope"]["selected_module_ids"] == [
        "GLIO-PROTEOGEN-M01-02",
        "GLIO-PROTEOGEN-M01-04",
    ]
    assert zero_ids.isdisjoint(one_ids)
    assert zero_ids | one_ids == {
        f"GLIO-PROTEOGEN-M01-{index:02d}" for index in range(1, EXPECTED_FOUR_MODULES + 1)
    }


@pytest.mark.parametrize(
    ("arguments", "failure"),
    [
        ({"shard_index": 0}, "required-together"),
        ({"shard_count": 2}, "required-together"),
        ({"shard_index": -1, "shard_count": 2}, "out-of-range"),
        ({"shard_index": 0, "shard_count": 2}, "exceeds-candidate"),
        ({"module_ids": []}, "non-empty-sequence"),
        ({"module_ids": "M01-01"}, "non-empty-sequence"),
        ({"module_ids": ["M01-01", "m01_01"]}, "duplicate-module-id"),
        ({"module_ids": ["M01-02"]}, "unknown-module-id"),
    ],
)
def test_invalid_selection_and_shards_are_rejected_strictly(
    tmp_path: Path,
    arguments: dict[str, object],
    failure: str,
) -> None:
    _make_repository(tmp_path)

    with pytest.raises(ModuleScopeError, match=failure):
        build_report(tmp_path, **arguments)


def test_content_digest_changes_when_associated_source_changes(tmp_path: Path) -> None:
    _make_repository(tmp_path)
    test_path = tmp_path / "tests" / "contract" / "test_m01_01_contract.py"
    before = build_report(tmp_path)

    test_path.write_text("# changed\n", encoding="utf-8")
    after = build_report(tmp_path)

    assert before["repository_content_digest"] != after["repository_content_digest"]
    assert before["validation_digest"] != after["validation_digest"]
    assert (
        before["modules"][0]["tests"]["content_digest"]
        != after["modules"][0]["tests"]["content_digest"]
    )


def test_discovery_reports_duplicates_orphans_and_associations(tmp_path: Path) -> None:
    _make_repository(tmp_path)
    _directory(tmp_path, "src/glio_proteogen/modules/c02/m01_01_duplicate")
    _directory(tmp_path, "src/glio_proteogen/contracts/m02_01")
    _directory(tmp_path, "src/glio_proteogen/modules/c03/m03_01_orphan")

    discovery = discover_repository(tmp_path)

    assert SOURCE_ID in discovery["duplicate_module_ids"]
    assert discovery["orphan_contracts"] == ["m02_01"]
    assert discovery["orphan_modules"] == ["m03_01"]
    assert discovery["modules"] == []


def test_empty_repository_fails_closed_instead_of_claiming_vacuous_success(
    tmp_path: Path,
) -> None:
    report = build_report(tmp_path)

    assert report["summary"]["valid"] is False
    assert report["discovery"]["closed_module_count"] == 0
    assert report["discovery"]["missing_roots"]
    assert "## Discovery failures" in render_markdown(report)


@pytest.mark.parametrize(
    ("schema_mutation", "failure_code"),
    [
        ({"$schema": "https://json-schema.org/draft/2019-09/schema"}, "schema_dialect"),
        ({"type": "not-a-json-schema-type"}, "schema_invalid"),
        (
            {"$id": "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-01:1.0.0:request"},
            "schema_module_id",
        ),
    ],
)
def test_schema_draft_and_identity_failures_are_authoritative(
    tmp_path: Path,
    schema_mutation: dict[str, object],
    failure_code: str,
) -> None:
    _make_repository(
        tmp_path,
        _RepositoryOptions(request_schema_mutation=schema_mutation),
    )

    contract = build_report(tmp_path)["modules"][0]["contract"]

    assert contract["passed"] is False
    assert any(code.startswith(failure_code) for code in contract["failures"])


def test_schema_export_must_be_deterministic(tmp_path: Path) -> None:
    _make_repository(tmp_path, _RepositoryOptions(nondeterministic_schema=True))

    contract = build_report(tmp_path)["modules"][0]["contract"]

    assert contract["deterministic"] is False
    assert "schema_nondeterministic" in contract["failures"]


def test_plugin_and_engine_import_failures_are_reported_without_crashing(
    tmp_path: Path,
) -> None:
    _make_repository(
        tmp_path,
        _RepositoryOptions(
            plugin_has_run=False,
            engine_source="raise RuntimeError('boom')\n",
        ),
    )

    implementation = build_report(tmp_path)["modules"][0]["implementation"]

    assert implementation["passed"] is False
    assert "plugin_run_missing" in implementation["failures"]
    assert any("RuntimeError" in code for code in implementation["failures"])


@pytest.mark.parametrize(
    ("source", "status", "callable_name", "required_arguments"),
    [
        (
            "if __name__ == '__main__':\n    print('{}')\n",
            "module",
            None,
            None,
        ),
        ("def evaluate():\n    return {}\n", "callable", "evaluate", 0),
        (
            "def run_evaluator(*, factory):\n    return factory()\n",
            "requires_arguments",
            "run_evaluator",
            EXPECTED_SINGLE_MODULE,
        ),
    ],
)
def test_evaluator_entrypoint_discovery(
    tmp_path: Path,
    source: str,
    status: str,
    callable_name: str | None,
    required_arguments: int | None,
) -> None:
    evaluator = tmp_path / "evals" / SOURCE_ID / "run.py"
    evaluator.parent.mkdir(parents=True)
    evaluator.write_text(source, encoding="utf-8")

    result = verifier._discover_evaluator(SOURCE_ID, (evaluator,), root=tmp_path)

    assert result["passed"] is True
    assert result["status"] == status
    assert result["callable"] == callable_name
    assert result["required_arguments"] == required_arguments


def test_evaluator_discovery_does_not_accept_a_main_string_literal(tmp_path: Path) -> None:
    evaluator = tmp_path / "evals" / SOURCE_ID / "run.py"
    evaluator.parent.mkdir(parents=True)
    evaluator.write_text('LABEL = "__main__"\n', encoding="utf-8")

    result = verifier._discover_evaluator(SOURCE_ID, (evaluator,), root=tmp_path)

    assert result["passed"] is False
    assert result["failures"] == ["evaluator_entrypoint_missing"]


def test_evaluator_discovery_prefers_canonical_runner_over_legacy_evaluate(
    tmp_path: Path,
) -> None:
    evaluator = tmp_path / "evals" / SOURCE_ID / "evaluator.py"
    evaluator.parent.mkdir(parents=True)
    evaluator.write_text(
        "def evaluate():\n    return True\n"
        "def run_evaluator():\n    return {'module_id': 'GLIO-PROTEOGEN-M01-01', "
        "'passed': True}\n",
        encoding="utf-8",
    )

    result = verifier._discover_evaluator(SOURCE_ID, (evaluator,), root=tmp_path)

    assert result["callable"] == "run_evaluator"


@pytest.mark.parametrize(
    ("payload", "expected_outcome", "failure"),
    [
        (
            {"module_id": MODULE_ID, "passed": True, "checks": [{"passed": True}]},
            "pass",
            None,
        ),
        (
            {"module_id": MODULE_ID, "passed": True, "checks": [{"passed": False}]},
            "fail",
            "evaluator_report_failed",
        ),
        (
            {
                "module_id": MODULE_ID,
                "passed": True,
                "checks": [{"passed": True}, {"detail": "missing result"}],
            },
            "fail",
            "evaluator_report_failed",
        ),
        (
            {"module_id": MODULE_ID, "module": "M02-01", "passed": True},
            "fail",
            "evaluator_module_id",
        ),
        (
            {"module_id": MODULE_ID, "detail": "no result"},
            "fail",
            "evaluator_result_ambiguous",
        ),
        (
            {"module_id": MODULE_ID, "total_cases": 3, "passed_cases": 3},
            "pass",
            None,
        ),
        (
            {
                "module_id": MODULE_ID,
                "total_cases": 3,
                "scenario_count": 4,
                "passed_cases": 4,
            },
            "fail",
            "evaluator_report_failed",
        ),
    ],
)
def test_evaluator_semantics_fail_closed(
    payload: object,
    expected_outcome: str,
    failure: str | None,
) -> None:
    normalized = normalize_evaluator_report(payload, expected_module_id=MODULE_ID)

    assert normalized["passed"] is (expected_outcome == "pass")
    if failure is None:
        assert normalized["failures"] == []
        assert normalized["report_digest"].startswith("sha256:")
    else:
        assert failure in normalized["failures"]


def test_optional_fresh_evaluator_execution_is_bound_into_state(tmp_path: Path) -> None:
    _make_repository(tmp_path)

    report = build_report(tmp_path, run_evaluators=True)
    module = report["modules"][0]

    assert report["summary"]["valid"] is True
    assert module["state"] == "validated-evaluator"
    assert module["evaluator"]["execution"]["passed"] is True
    assert module["evaluator"]["execution"]["stdout_digest"].startswith("sha256:")


def test_optional_evaluator_false_report_fails_even_with_exit_zero(tmp_path: Path) -> None:
    _make_repository(tmp_path, _RepositoryOptions(evaluator_passed=False))

    report = build_report(tmp_path, run_evaluators=True)

    assert report["summary"]["valid"] is False
    assert report["modules"][0]["state"] == "failed"
    assert "evaluator_execution:evaluator_report_failed" in report["modules"][0]["failure_codes"]


def test_benchmark_discovery_prefers_canonical_callable_and_bounds_iterations(
    tmp_path: Path,
) -> None:
    benchmark = tmp_path / "evals" / SOURCE_ID / "benchmark.py"
    benchmark.parent.mkdir(parents=True)
    benchmark.write_text(
        "def benchmark():\n    return {}\n"
        "def run():\n    return {}\n"
        "def run_benchmark(iterations=100):\n    return {}\n",
        encoding="utf-8",
    )

    result = verifier._discover_benchmark(SOURCE_ID, (benchmark,), root=tmp_path)

    assert result["passed"] is True
    assert result["callable"] == "run_benchmark"
    assert result["invocation"] == "keyword_iterations"
    assert result["smoke_iterations"] == BENCHMARK_SMOKE_ITERATIONS


@pytest.mark.parametrize(
    ("signature", "invocation", "expected_outcome"),
    [
        ("iterations, /", "positional_iterations", "pass"),
        ("iterations=50", "keyword_iterations", "pass"),
        ("", "no_arguments", "pass"),
        ("factory", "requires_arguments", "fail"),
        ("iterations=50, *args", "requires_arguments", "fail"),
    ],
)
def test_benchmark_callable_signature_discovery_is_conservative(
    tmp_path: Path,
    signature: str,
    invocation: str,
    expected_outcome: str,
) -> None:
    benchmark = tmp_path / "evals" / SOURCE_ID / "benchmark.py"
    benchmark.parent.mkdir(parents=True)
    benchmark.write_text(
        f"def run_benchmark({signature}):\n    return {{}}\n",
        encoding="utf-8",
    )

    result = verifier._discover_benchmark(SOURCE_ID, (benchmark,), root=tmp_path)

    assert result["passed"] is (expected_outcome == "pass")
    assert result["invocation"] == invocation


def test_benchmark_discovery_rejects_fixture_only_file_and_supports_module_main(
    tmp_path: Path,
) -> None:
    fixture_only = tmp_path / "benchmarks" / "m01_01_fixture.py"
    fixture_only.parent.mkdir(parents=True)
    fixture_only.write_text(
        "def test_latency(benchmark):\n    benchmark(lambda: None)\n",
        encoding="utf-8",
    )
    fixture_result = verifier._discover_benchmark(
        SOURCE_ID,
        (fixture_only,),
        root=tmp_path,
    )
    module_main = tmp_path / "benchmarks" / "m01_01_main.py"
    module_main.write_text(
        "if __name__ == '__main__':\n    print('{}')\n",
        encoding="utf-8",
    )
    main_result = verifier._discover_benchmark(SOURCE_ID, (module_main,), root=tmp_path)

    assert fixture_result["passed"] is False
    assert fixture_result["failures"] == ["benchmark_entrypoint_missing"]
    assert main_result["passed"] is True
    assert main_result["invocation"] == "module"


@pytest.mark.parametrize(
    ("payload", "failure"),
    [
        (True, "benchmark_report_not_object"),
        ({}, "benchmark_module_id"),
        (
            {"module_id": "GLIO-PROTEOGEN-M02-01", "passed": True, "budget_ns": 10},
            "benchmark_module_id",
        ),
        (
            {"module_id": MODULE_ID, "passed": True},
            "benchmark_budget_evidence_missing",
        ),
        (
            {"module_id": MODULE_ID, "mean_budget_ns": 10},
            "benchmark_pass_evidence_missing",
        ),
        (
            {"module_id": MODULE_ID, "passed": False, "mean_budget_ns": 10},
            "benchmark_report_failed",
        ),
    ],
)
def test_benchmark_report_normalization_fails_closed(
    payload: object,
    failure: str,
) -> None:
    result = normalize_benchmark_report(payload, expected_module_id=MODULE_ID)

    assert result["passed"] is False
    assert result["failures"] == [failure]


def test_benchmark_report_accepts_explicit_component_passes_and_nested_budgets() -> None:
    result = normalize_benchmark_report(
        {
            "module_id": MODULE_ID,
            "mean_budget_pass": True,
            "p95_budget_pass": True,
            "budgets_ns": {"mean": 10, "p95": 20},
        },
        expected_module_id=MODULE_ID,
    )

    assert result["passed"] is True
    assert result["pass_evidence_count"] == EXPECTED_TWO_ARTIFACTS
    assert result["budget_evidence_count"] == EXPECTED_TWO_ARTIFACTS
    assert result["pass_evidence"] == [
        {"path": "mean_budget_pass", "passed": True},
        {"path": "p95_budget_pass", "passed": True},
    ]
    assert result["budget_evidence"] == [
        {"path": "budgets_ns.mean", "value": 10},
        {"path": "budgets_ns.p95", "value": 20},
    ]


def test_optional_benchmark_execution_uses_smoke_iterations_and_changes_state(
    tmp_path: Path,
) -> None:
    _make_repository(
        tmp_path,
        _RepositoryOptions(benchmark_source=_passing_benchmark_source(MODULE_ID)),
    )

    report = build_report(tmp_path, run_benchmarks=True)
    module = report["modules"][0]

    assert report["summary"]["valid"] is True
    assert report["mode"] == "benchmark"
    assert report["summary"]["validated_benchmark"] == EXPECTED_SINGLE_MODULE
    assert module["state"] == "validated-benchmark"
    assert module["benchmarks"]["execution"]["passed"] is True
    assert module["benchmarks"]["execution"]["smoke_iterations"] == BENCHMARK_SMOKE_ITERATIONS
    assert "benchmark-execution" in module["validation_basis"]


def test_combined_evaluator_and_benchmark_state_is_explicit(tmp_path: Path) -> None:
    _make_repository(
        tmp_path,
        _RepositoryOptions(benchmark_source=_passing_benchmark_source(MODULE_ID)),
    )

    report = build_report(tmp_path, run_evaluators=True, run_benchmarks=True)

    assert report["summary"]["valid"] is True
    assert report["mode"] == "evaluator+benchmark"
    assert report["modules"][0]["state"] == "validated-evaluator-benchmark"
    assert report["summary"]["validated_evaluator_benchmark"] == EXPECTED_SINGLE_MODULE


@pytest.mark.parametrize(
    ("benchmark_source", "timeout", "failure"),
    [
        ("def run_benchmark():\n    return True\n", 1.0, "benchmark_report_not_object"),
        ("def run_benchmark():\n    return {}\n", 1.0, "benchmark_module_id"),
        (
            "def run_benchmark():\n    raise SystemExit(3)\n",
            1.0,
            "benchmark_exit_nonzero",
        ),
        (
            "import time\ndef run_benchmark():\n    time.sleep(1)\n    return {}\n",
            0.01,
            "benchmark_timeout",
        ),
    ],
)
def test_benchmark_execution_process_failures_are_closed(
    tmp_path: Path,
    benchmark_source: str,
    timeout: float,
    failure: str,
) -> None:
    _make_repository(
        tmp_path,
        _RepositoryOptions(benchmark_source=benchmark_source),
    )

    report = build_report(
        tmp_path,
        run_benchmarks=True,
        benchmark_timeout_seconds=timeout,
    )

    assert report["summary"]["valid"] is False
    assert f"benchmark_execution:{failure}" in report["modules"][0]["failure_codes"]


@pytest.mark.parametrize(
    "stdout",
    [
        "not-json",
        (f'{{"module_id":"{MODULE_ID}","passed":true,"mean_budget_ns":1,"mean_budget_ns":2}}'),
        f'{{"module_id":"{MODULE_ID}","passed":true,"mean_budget_ns":NaN}}',
    ],
)
def test_benchmark_malformed_module_output_fails_closed(
    tmp_path: Path,
    stdout: str,
) -> None:
    _make_repository(
        tmp_path,
        _RepositoryOptions(benchmark_source=f"if __name__ == '__main__':\n    print({stdout!r})\n"),
    )

    report = build_report(tmp_path, run_benchmarks=True)

    assert "benchmark_execution:benchmark_output_not_json" in report["modules"][0]["failure_codes"]


def test_benchmark_output_limit_is_enforced(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    completed = verifier.subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout="x" * (MAX_BENCHMARK_OUTPUT_BYTES + 1),
        stderr="",
    )

    def completed_process(*_args: object, **_kwargs: object) -> object:
        return completed

    monkeypatch.setattr(verifier.subprocess, "run", completed_process)
    discovery = {
        "passed": True,
        "entrypoint": "evals.m01_01.benchmark",
        "callable": "run_benchmark",
        "invocation": "no_arguments",
        "smoke_iterations": None,
    }

    result = verifier._execute_benchmark(
        discovery,
        expected_module_id=MODULE_ID,
        root=tmp_path,
        timeout_seconds=1.0,
    )

    assert result["failures"] == ["benchmark_output_too_large"]


@pytest.mark.parametrize("timeout", [0.0, -1.0, float("nan"), True])
def test_benchmark_timeout_must_be_positive_finite(
    tmp_path: Path,
    timeout: object,
) -> None:
    _make_repository(tmp_path)

    with pytest.raises(ValueError, match="benchmark timeout"):
        build_report(
            tmp_path,
            run_benchmarks=True,
            benchmark_timeout_seconds=timeout,
        )


def test_cli_rejects_invalid_benchmark_timeout_cleanly(tmp_path: Path) -> None:
    _make_repository(tmp_path)

    with pytest.raises(SystemExit) as caught:
        verifier.main(
            [
                "--repository-root",
                str(tmp_path),
                "--run-benchmarks",
                "--benchmark-timeout-seconds",
                "nan",
            ]
        )

    assert caught.value.code == CLI_USAGE_ERROR


def test_benchmark_execution_respects_explicit_module_selection(tmp_path: Path) -> None:
    _make_repository_with_modules(tmp_path, module_count=EXPECTED_TWO_ARTIFACTS)
    selected_benchmark = tmp_path / "evals" / "m01_02" / "benchmark.py"
    selected_benchmark.write_text(
        _passing_benchmark_source("GLIO-PROTEOGEN-M01-02"),
        encoding="utf-8",
    )

    report = build_report(
        tmp_path,
        module_ids=["M01-02"],
        run_benchmarks=True,
    )

    assert report["summary"]["valid"] is True
    assert report["scope"]["selected_module_ids"] == ["GLIO-PROTEOGEN-M01-02"]


def test_cli_runs_module_benchmark_with_independent_timeout(tmp_path: Path) -> None:
    _make_repository(
        tmp_path,
        _RepositoryOptions(benchmark_source=_passing_benchmark_source(MODULE_ID)),
    )
    output = tmp_path / "benchmark-receipt.json"

    exit_code = verifier.main(
        [
            "--repository-root",
            str(tmp_path),
            "--run-benchmarks",
            "--benchmark-timeout-seconds",
            "1.5",
            "--output",
            str(output),
        ]
    )
    receipt = json.loads(output.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert receipt["mode"] == "benchmark"
    assert receipt["modules"][0]["benchmarks"]["execution"]["passed"] is True


def test_evidence_json_must_parse_and_cannot_claim_another_module(tmp_path: Path) -> None:
    _make_repository(tmp_path)
    evidence = tmp_path / "release-evidence" / SOURCE_ID / "evaluation.json"
    evidence.write_text('{"module_id":"GLIO-PROTEOGEN-M02-01"}\n', encoding="utf-8")

    result = build_report(tmp_path)["modules"][0]

    assert result["evidence"]["passed"] is False
    assert result["evidence"]["module_id_mismatches"] == ["evaluation.json"]
    assert "evidence:closure" in result["failure_codes"]


def test_junit_evidence_binds_module_execution_and_outcomes(tmp_path: Path) -> None:
    _make_repository(tmp_path)
    junit = _write_junit(tmp_path, SOURCE_ID)

    first = build_report(tmp_path, junit_xml=junit)
    second = build_report(tmp_path, junit_xml=[junit])
    execution = first["modules"][0]["tests"]["execution"]

    assert first == second
    assert first["summary"]["valid"] is True
    assert first["test_evidence"]["junit"]["passed"] is True
    assert first["test_evidence"]["junit"]["evidence_digest"].startswith("sha256:")
    assert execution["passed"] is True
    assert execution["testcase_count"] == EXPECTED_SINGLE_MODULE
    assert execution["passed_count"] == EXPECTED_SINGLE_MODULE
    assert "pytest-junit" in first["modules"][0]["validation_basis"]
    assert "## Test evidence" in render_markdown(first)


@pytest.mark.parametrize("outcome", ["failure", "error", "skipped"])
def test_junit_nonpassing_outcomes_fail_closed(tmp_path: Path, outcome: str) -> None:
    _make_repository(tmp_path)
    junit = _write_junit(tmp_path, SOURCE_ID, outcome=outcome)

    report = build_report(tmp_path, junit_xml=junit)

    assert report["summary"]["valid"] is False
    assert report["test_evidence"]["junit"]["passed"] is False
    assert report["modules"][0]["state"] == "failed"
    assert any(code.startswith("test_execution:") for code in report["modules"][0]["failure_codes"])


def test_junit_missing_malformed_and_ambiguous_evidence_fails_closed(tmp_path: Path) -> None:
    _make_repository_with_modules(tmp_path, module_count=EXPECTED_TWO_ARTIFACTS)
    missing = tmp_path / "missing-junit.xml"
    missing_report = build_report(tmp_path, module_ids=["M01-01"], junit_xml=missing)
    malformed = tmp_path / "malformed-junit.xml"
    malformed.write_text("<testsuite>", encoding="utf-8")
    malformed_report = build_report(tmp_path, module_ids=["M01-01"], junit_xml=malformed)
    count_mismatch = _write_junit(tmp_path, SOURCE_ID, name="count-mismatch.xml")
    count_mismatch.write_text(
        count_mismatch.read_text(encoding="utf-8").replace('tests="1"', 'tests="2"'),
        encoding="utf-8",
    )
    count_report = build_report(tmp_path, module_ids=["M01-01"], junit_xml=count_mismatch)
    ambiguous = _write_junit(tmp_path, "m01_01", name="ambiguous-junit.xml")
    ambiguous.write_text(
        ambiguous.read_text(encoding="utf-8").replace(
            "tests.contract.test_m01_01_contract",
            "tests.contract.test_m01_02_contract",
        ),
        encoding="utf-8",
    )
    ambiguous_report = build_report(tmp_path, junit_xml=ambiguous)

    assert "document-unreadable" in missing_report["test_evidence"]["junit"]["failures"]
    assert "xml-malformed" in malformed_report["test_evidence"]["junit"]["failures"]
    assert "testsuite-count-mismatch" in count_report["test_evidence"]["junit"]["failures"]
    assert "testcase-module-id-ambiguous" in ambiguous_report["test_evidence"]["junit"]["failures"]
    assert missing_report["summary"]["valid"] is False
    assert malformed_report["summary"]["valid"] is False
    assert count_report["summary"]["valid"] is False
    assert ambiguous_report["summary"]["valid"] is False


def test_junit_test_name_is_non_authoritative(tmp_path: Path) -> None:
    _make_repository_with_modules(tmp_path, module_count=EXPECTED_TWO_ARTIFACTS)
    junit = _write_junit(
        tmp_path,
        SOURCE_ID,
        testcase_name="test_rejects_m01_02_and_unknown_m01_99",
    )

    report = build_report(tmp_path, module_ids=["M01-01"], junit_xml=junit)
    evidence = report["test_evidence"]["junit"]
    execution = report["modules"][0]["tests"]["execution"]

    assert report["summary"]["valid"] is True
    assert evidence["failures"] == []
    assert evidence["associated_testcase_count"] == EXPECTED_SINGLE_MODULE
    assert execution["testcase_count"] == EXPECTED_SINGLE_MODULE


def test_junit_shared_location_is_nonbinding_without_inflating_modules(tmp_path: Path) -> None:
    _make_repository_with_modules(tmp_path, module_count=EXPECTED_TWO_ARTIFACTS)
    junit = tmp_path / "shared-junit.xml"
    junit.write_text(
        '<testsuites><testsuite tests="3">'
        '<testcase file="tests/contract/test_m01_01_contract.py" '
        'classname="tests.contract.test_m01_01_contract" name="test_first" />'
        '<testcase file="tests/contract/test_m01_02_contract.py" '
        'classname="tests.contract.test_m01_02_contract" name="test_second" />'
        '<testcase file="tests/contract/test_m01_01_m01_02_contract.py" '
        'classname="tests.contract.test_m01_01_m01_02_contract" name="test_shared" />'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )

    report = build_report(tmp_path, junit_xml=junit)
    evidence = report["test_evidence"]["junit"]

    assert report["summary"]["valid"] is True
    assert evidence["testcase_count"] == EXPECTED_THREE_TESTCASES
    assert evidence["associated_testcase_count"] == EXPECTED_TWO_ARTIFACTS
    assert evidence["unassociated_testcase_count"] == EXPECTED_SINGLE_MODULE
    assert all(
        module["tests"]["execution"]["testcase_count"] == EXPECTED_SINGLE_MODULE
        for module in report["modules"]
    )


def test_junit_unknown_structural_owner_fails_closed(tmp_path: Path) -> None:
    _make_repository(tmp_path)
    junit = _write_junit(tmp_path, SOURCE_ID)
    junit.write_text(
        junit.read_text(encoding="utf-8").replace(
            "tests.contract.test_m01_01_contract",
            "tests.contract.test_m01_99_contract",
        ),
        encoding="utf-8",
    )

    report = build_report(tmp_path, junit_xml=junit)
    evidence = report["test_evidence"]["junit"]

    assert report["summary"]["valid"] is False
    assert "testcase-unknown-module-id" in evidence["failures"]
    assert evidence["associated_testcase_count"] == 0
    assert evidence["unassociated_testcase_count"] == EXPECTED_SINGLE_MODULE
    assert report["modules"][0]["tests"]["execution"]["failures"] == [
        "test-execution-evidence-invalid",
        "test-execution-missing",
    ]


def test_junit_allows_disclosed_skips_when_a_module_has_a_passing_test(tmp_path: Path) -> None:
    _make_repository(tmp_path)
    junit = tmp_path / "mixed-outcomes.xml"
    junit.write_text(
        '<testsuites><testsuite tests="2" skipped="1">'
        '<testcase file="tests/contract/test_m01_01_contract.py" '
        'classname="tests.contract.test_m01_01_contract" name="test_passes" />'
        '<testcase file="tests/contract/test_m01_01_contract.py" '
        'classname="tests.contract.test_m01_01_contract" name="test_optional">'
        '<skipped message="optional historical artifact unavailable" />'
        "</testcase></testsuite></testsuites>",
        encoding="utf-8",
    )

    report = build_report(tmp_path, junit_xml=junit)
    execution = report["modules"][0]["tests"]["execution"]

    assert report["summary"]["valid"] is True
    assert execution["passed_count"] == EXPECTED_SINGLE_MODULE
    assert execution["skipped_count"] == EXPECTED_SINGLE_MODULE
    assert execution["failures"] == []


def test_junit_requires_execution_for_every_selected_module(tmp_path: Path) -> None:
    _make_repository_with_modules(tmp_path, module_count=EXPECTED_TWO_ARTIFACTS)
    junit = _write_junit(tmp_path, SOURCE_ID)

    report = build_report(tmp_path, junit_xml=junit)
    second = next(module for module in report["modules"] if module["source_id"] == "m01_02")

    assert report["summary"]["valid"] is False
    assert second["tests"]["execution"]["failures"] == ["test-execution-missing"]


def test_coverage_json_binds_selected_governed_source_and_thresholds(tmp_path: Path) -> None:
    _make_repository(tmp_path)
    coverage = _write_coverage_json(tmp_path, [SOURCE_ID])

    report = build_report(
        tmp_path,
        coverage_reports=coverage,
        minimum_line_coverage_percent=100.0,
        minimum_branch_coverage_percent=100.0,
    )
    module_coverage = report["modules"][0]["coverage"]

    assert report["summary"]["valid"] is True
    assert report["test_evidence"]["coverage"]["passed"] is True
    assert report["test_evidence"]["coverage"]["evidence_digest"].startswith("sha256:")
    assert module_coverage["passed"] is True
    assert module_coverage["missing_source_files"] == []
    assert module_coverage["line_coverage"]["percent"] == FULL_COVERAGE_PERCENT
    assert module_coverage["branch_coverage"]["percent"] == FULL_COVERAGE_PERCENT


def test_coverage_threshold_and_missing_source_fail_closed(tmp_path: Path) -> None:
    _make_repository(tmp_path)
    below = _write_coverage_json(tmp_path, [SOURCE_ID], missing_line=True)
    below_report = build_report(
        tmp_path,
        coverage_reports=below,
        minimum_line_coverage_percent=100.0,
    )
    incomplete = _write_coverage_json(
        tmp_path,
        [SOURCE_ID],
        name="incomplete-coverage.json",
        omit_engine=True,
    )
    incomplete_report = build_report(tmp_path, coverage_reports=incomplete)
    out_of_range = _write_coverage_json(
        tmp_path,
        [SOURCE_ID],
        name="out-of-range-coverage.json",
    )
    out_of_range_payload = json.loads(out_of_range.read_text(encoding="utf-8"))
    first_file = next(iter(out_of_range_payload["files"].values()))
    first_file["executed_lines"] = [999_999]
    out_of_range.write_text(json.dumps(out_of_range_payload), encoding="utf-8")
    out_of_range_report = build_report(tmp_path, coverage_reports=out_of_range)

    assert "line-coverage-below-threshold" in below_report["modules"][0]["coverage"]["failures"]
    assert "coverage-source-missing" in incomplete_report["modules"][0]["coverage"]["failures"]
    assert (
        "coverage-source-lines-invalid" in out_of_range_report["modules"][0]["coverage"]["failures"]
    )
    assert below_report["summary"]["valid"] is False
    assert incomplete_report["summary"]["valid"] is False
    assert out_of_range_report["summary"]["valid"] is False


def test_coverage_xml_is_supported_and_malformed_input_fails_closed(tmp_path: Path) -> None:
    _make_repository(tmp_path)
    coverage_xml = _write_coverage_xml(tmp_path, [SOURCE_ID])
    valid = build_report(tmp_path, coverage_reports=coverage_xml)
    malformed = tmp_path / "coverage-malformed.xml"
    malformed.write_text("<!DOCTYPE coverage><coverage/>", encoding="utf-8")
    invalid = build_report(tmp_path, coverage_reports=malformed)

    assert valid["summary"]["valid"] is True
    assert valid["test_evidence"]["coverage"]["documents"][0]["media_type"] == ("application/xml")
    assert invalid["summary"]["valid"] is False
    assert "xml-doctype-or-entity" in invalid["test_evidence"]["coverage"]["failures"]


def test_coverage_xml_ignores_foreign_repository_shadow_paths(tmp_path: Path) -> None:
    _make_repository(tmp_path)
    coverage_xml = _write_coverage_xml(tmp_path, [SOURCE_ID])
    foreign_shadow = (
        tmp_path.parent / "foreign-repository" / _governed_source_paths(SOURCE_ID)[0]
    ).as_posix()
    coverage_xml.write_text(
        coverage_xml.read_text(encoding="utf-8").replace(
            "<classes>",
            f'<classes><class filename="{foreign_shadow}"><lines /></class>',
        ),
        encoding="utf-8",
    )

    report = build_report(tmp_path, coverage_reports=coverage_xml)
    evidence = report["test_evidence"]["coverage"]
    module_coverage = report["modules"][0]["coverage"]

    assert report["summary"]["valid"] is True
    assert evidence["failures"] == []
    assert evidence["reported_source_file_count"] == len(_governed_source_paths(SOURCE_ID))
    assert module_coverage["invalid_source_files"] == []
    assert module_coverage["missing_source_files"] == []


def test_coverage_xml_foreign_only_evidence_fails_closed(tmp_path: Path) -> None:
    _make_repository(tmp_path)
    foreign_path = (
        tmp_path.parent / "foreign-repository" / _governed_source_paths(SOURCE_ID)[0]
    ).as_posix()
    coverage_xml = tmp_path / "foreign-only-coverage.xml"
    coverage_xml.write_text(
        f'<coverage><packages><package><classes><class filename="{foreign_path}">'
        '<lines><line number="1" hits="1" /></lines></class>'
        "</classes></package></packages></coverage>",
        encoding="utf-8",
    )

    report = build_report(tmp_path, coverage_reports=coverage_xml)

    assert report["summary"]["valid"] is False
    assert report["test_evidence"]["coverage"]["failures"] == [
        "coverage-no-governed-source"
    ]
    assert "coverage-source-missing" in report["modules"][0]["coverage"]["failures"]


def test_coverage_xml_rejects_duplicate_paths_within_repository(tmp_path: Path) -> None:
    _make_repository(tmp_path)
    coverage_xml = _write_coverage_xml(tmp_path, [SOURCE_ID])
    source_path = _governed_source_paths(SOURCE_ID)[0]
    absolute_alias = (tmp_path / source_path).resolve().as_posix()
    coverage_xml.write_text(
        coverage_xml.read_text(encoding="utf-8").replace(
            "<classes>",
            f'<classes><class filename="{absolute_alias}">'
            '<lines><line number="1" hits="1" /></lines></class>',
        ),
        encoding="utf-8",
    )

    report = build_report(tmp_path, coverage_reports=coverage_xml)

    assert report["summary"]["valid"] is False
    assert "coverage-path-duplicate" in report["test_evidence"]["coverage"]["failures"]


def test_coverage_evidence_is_scoped_to_selected_modules(tmp_path: Path) -> None:
    _make_repository_with_modules(tmp_path, module_count=EXPECTED_TWO_ARTIFACTS)
    coverage = _write_coverage_json(tmp_path, ["m01_02"])

    report = build_report(
        tmp_path,
        module_ids=["M01-02"],
        coverage_reports=coverage,
        minimum_line_coverage_percent=100.0,
    )

    assert report["summary"]["valid"] is True
    assert report["scope"]["selected_module_ids"] == ["GLIO-PROTEOGEN-M01-02"]
    assert report["modules"][0]["coverage"]["passed"] is True


def test_requested_coverage_rejects_malformed_duplicate_and_invalid_configuration(
    tmp_path: Path,
) -> None:
    _make_repository(tmp_path)
    malformed = tmp_path / "coverage.json"
    malformed.write_text("[]", encoding="utf-8")
    malformed_report = build_report(tmp_path, coverage_reports=malformed)
    duplicate_key = tmp_path / "duplicate-key-coverage.json"
    coverage_value = json.dumps(
        {
            "executed_lines": [1],
            "missing_lines": [],
            "executed_branches": [],
            "missing_branches": [],
        }
    )
    coverage_path = _governed_source_paths(SOURCE_ID)[0]
    duplicate_key.write_text(
        f'{{"files":{{"{coverage_path}":{coverage_value},"{coverage_path}":{coverage_value}}}}}',
        encoding="utf-8",
    )
    duplicate_key_report = build_report(tmp_path, coverage_reports=duplicate_key)
    duplicate = _write_coverage_json(tmp_path, [SOURCE_ID], name="duplicate.json")
    duplicate_copy = duplicate.with_name("copy.json")
    duplicate_copy.write_bytes(duplicate.read_bytes())
    duplicate_report = build_report(tmp_path, coverage_reports=[duplicate, duplicate_copy])

    assert malformed_report["summary"]["valid"] is False
    assert "coverage-json-shape" in malformed_report["test_evidence"]["coverage"]["failures"]
    assert (
        "coverage-json-malformed" in duplicate_key_report["test_evidence"]["coverage"]["failures"]
    )
    assert (
        "coverage-path-duplicate-across-documents"
        in duplicate_report["test_evidence"]["coverage"]["failures"]
    )
    with pytest.raises(EvidenceConfigurationError, match="threshold-without-report"):
        build_report(tmp_path, minimum_line_coverage_percent=95.0)


@pytest.mark.parametrize("threshold", INVALID_COVERAGE_THRESHOLDS)
def test_coverage_thresholds_are_strict_finite_percentages(
    tmp_path: Path,
    threshold: object,
) -> None:
    _make_repository(tmp_path)
    coverage = _write_coverage_json(tmp_path, [SOURCE_ID])

    with pytest.raises(EvidenceConfigurationError, match="line-coverage-threshold"):
        build_report(
            tmp_path,
            coverage_reports=coverage,
            minimum_line_coverage_percent=threshold,
        )


def test_cli_accepts_selection_sharding_and_test_evidence(
    tmp_path: Path,
) -> None:
    _make_repository_with_modules(tmp_path, module_count=EXPECTED_TWO_ARTIFACTS)
    junit = _write_junit(tmp_path, "m01_02")
    output = tmp_path / "receipt.json"

    exit_code = verifier.main(
        [
            "--repository-root",
            str(tmp_path),
            "--module",
            "M01-01",
            "--module",
            "M01-02",
            "--shard-index",
            "1",
            "--shard-count",
            "2",
            "--junit-xml",
            str(junit),
            "--output",
            str(output),
        ]
    )
    receipt = json.loads(output.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert receipt["scope"]["mode"] == "selection+shard"
    assert receipt["scope"]["selected_module_ids"] == ["GLIO-PROTEOGEN-M01-02"]
    assert receipt["test_evidence"]["junit"]["passed"] is True


def test_verify_raises_for_a_failed_receipt(tmp_path: Path) -> None:
    _make_repository(tmp_path, _RepositoryOptions(plugin_has_run=False))

    with pytest.raises(ModuleValidationError, match="1 module"):
        verify(tmp_path)


def _make_repository(
    root: Path,
    options: _RepositoryOptions | None = None,
) -> None:
    _add_module(root, SOURCE_ID, MODULE_ID, options or _RepositoryOptions())


def _make_repository_with_modules(root: Path, *, module_count: int) -> None:
    for index in range(1, module_count + 1):
        source_id = f"m01_{index:02d}"
        module_id = f"GLIO-PROTEOGEN-M01-{index:02d}"
        _add_module(root, source_id, module_id, _RepositoryOptions())


def _passing_benchmark_source(module_id: str) -> str:
    return (
        "def run_benchmark(iterations=100):\n"
        "    return {\n"
        f"        'module_id': {module_id!r},\n"
        f"        'passed': iterations == {BENCHMARK_SMOKE_ITERATIONS},\n"
        "        'mean_budget_ns': 1000,\n"
        "        'p95_budget_ns': 2000,\n"
        "        'iterations': iterations,\n"
        "    }\n"
    )


def _add_module(
    root: Path,
    source_id: str,
    module_id: str,
    settings: _RepositoryOptions,
) -> None:
    contract = _directory(root, f"src/glio_proteogen/contracts/{source_id}")
    module = _directory(root, f"src/glio_proteogen/modules/c01/{source_id}_example")
    evaluator = _directory(root, f"evals/{source_id}")
    tests = _directory(root, "tests/contract")
    evidence = _directory(root, f"release-evidence/{source_id}")
    for package in (
        root / "src" / "glio_proteogen",
        root / "src" / "glio_proteogen" / "contracts",
        contract,
        root / "src" / "glio_proteogen" / "modules",
        root / "src" / "glio_proteogen" / "modules" / "c01",
        module,
    ):
        (package / "__init__.py").write_text("", encoding="utf-8")

    schema_documents = _schemas(module_id, settings.request_schema_mutation or {})
    schema_source = (
        "import copy\n"
        f"SCHEMAS = {schema_documents!r}\n"
        + ("COUNTER = 0\n" if settings.nondeterministic_schema else "")
        + "def contract_json_schemas():\n"
        + ("    global COUNTER\n    COUNTER += 1\n" if settings.nondeterministic_schema else "")
        + "    value = copy.deepcopy(SCHEMAS)\n"
        + (
            "    value['request']['title'] = str(COUNTER)\n"
            if settings.nondeterministic_schema
            else ""
        )
        + "    return value\n"
    )
    (contract / "schema.py").write_text(schema_source, encoding="utf-8")
    (module / "service.py").write_text("class Service:\n    pass\n", encoding="utf-8")
    run_source = (
        "    def run(self, value):\n        return value\n" if settings.plugin_has_run else ""
    )
    (module / "plugin.py").write_text(
        f"class {source_id.replace('_', '').upper()}Plugin:\n"
        f"    def validate(self, value):\n        return value\n{run_source}",
        encoding="utf-8",
    )
    (module / "engine.py").write_text(settings.engine_source, encoding="utf-8")
    (evaluator / "run.py").write_text(
        "import json\n"
        "if __name__ == '__main__':\n"
        f"    print(json.dumps({{'module_id': {module_id!r}, "
        f"'passed': {settings.evaluator_passed!r}}}))\n",
        encoding="utf-8",
    )
    (evaluator / "benchmark.py").write_text(settings.benchmark_source, encoding="utf-8")
    (tests / f"test_{source_id}_contract.py").write_text("", encoding="utf-8")
    (evidence / "evaluation.json").write_text(
        json.dumps({"module_id": module_id, "passed": True}) + "\n",
        encoding="utf-8",
    )


def _schemas(module_id: str, request_mutation: dict[str, object]) -> dict[str, dict[str, object]]:
    base = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "x-glio-contract": {"moduleId": module_id, "contractVersion": "1.0.0"},
    }
    request = {
        **base,
        "$id": f"urn:aurora-neuro:glio-proteogen:{module_id}:1.0.0:request",
        **request_mutation,
    }
    output = {
        **base,
        "$id": f"urn:aurora-neuro:glio-proteogen:{module_id}:1.0.0:output",
    }
    return {"request": request, "output": output}


def _write_junit(
    root: Path,
    source_id: str,
    *,
    outcome: str = "passed",
    name: str = "junit.xml",
    testcase_name: str = "test_contract",
) -> Path:
    outcome_xml = "" if outcome == "passed" else f'<{outcome} message="evidence" />'
    path = root / name
    path.write_text(
        '<testsuites><testsuite tests="1">'
        f'<testcase file="tests/contract/test_{source_id}_contract.py" '
        f'classname="tests.contract.test_{source_id}_contract" name="{testcase_name}">'
        f"{outcome_xml}</testcase></testsuite></testsuites>",
        encoding="utf-8",
    )
    return path


def _governed_source_paths(source_id: str) -> list[str]:
    return [
        f"src/glio_proteogen/contracts/{source_id}/schema.py",
        f"src/glio_proteogen/modules/c01/{source_id}_example/service.py",
        f"src/glio_proteogen/modules/c01/{source_id}_example/plugin.py",
        f"src/glio_proteogen/modules/c01/{source_id}_example/engine.py",
    ]


def _write_coverage_json(
    root: Path,
    source_ids: list[str],
    *,
    name: str = "coverage.json",
    missing_line: bool = False,
    omit_engine: bool = False,
) -> Path:
    source_paths = [path for source_id in source_ids for path in _governed_source_paths(source_id)]
    if omit_engine:
        source_paths = [path for path in source_paths if not path.endswith("engine.py")]
    files = {
        path: {
            "executed_lines": [] if missing_line and path.endswith("engine.py") else [1],
            "missing_lines": [1] if missing_line and path.endswith("engine.py") else [],
            "executed_branches": [],
            "missing_branches": [],
        }
        for path in source_paths
    }
    output = root / name
    output.write_text(json.dumps({"meta": {"format": 3}, "files": files}), encoding="utf-8")
    return output


def _write_coverage_xml(root: Path, source_ids: list[str]) -> Path:
    classes = "".join(
        f'<class filename="{path.removeprefix("src/")}">'
        '<lines><line number="1" hits="1" /></lines></class>'
        for source_id in source_ids
        for path in _governed_source_paths(source_id)
    )
    output = root / "coverage.xml"
    output.write_text(
        f"<coverage><packages><package><classes>{classes}</classes></package></packages></coverage>",
        encoding="utf-8",
    )
    return output


def _directory(root: Path, relative: str) -> Path:
    path = root / relative
    path.mkdir(parents=True, exist_ok=True)
    return path
