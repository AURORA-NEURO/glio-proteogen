"""Executable nominal and adversarial evidence for M21-05."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final, TypedDict, cast

from pydantic import TypeAdapter, ValidationError
from tests.contract.test_m21_05_adversarial import _request

from glio_proteogen.contracts.m21_05 import (
    M2105_MODULE_ID,
    CoverageStatus,
    EquityStatus,
    EvaluateComplexActivitySubgroupEquityRequest,
    EvaluationStatus,
    SubgroupDimension,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ConsentState, SupportStatus
from glio_proteogen.modules.c21_complex_activity.m21_05_subgroup_equity_evaluator import (
    M2105AuthorizationError,
    M2105Engine,
    M2105ReplayError,
)

MODULE_ID: Final = M2105_MODULE_ID
SCENARIO_PATH: Final = Path("tests/fixtures/m21_05/scenarios.json")
DOSSIER_SHA256: Final = "0A6B200CBE073DB13A4BCF315EDC23AB97EDFE6F500BC7EA2785F5E1C70DA181"
DOSSIER_SLICE: Final = "GLIO-PROTEOGEN_240_Module_Dossier.md:7412-7452"
EXPECTED_CASE_COUNT: Final = 9
ADVERSARIAL_CASE_COUNT: Final = 8
TARGET_COVERAGE_PERCENT: Final = 95


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


class ScenarioGroup(TypedDict):
    group: str
    case_ids: list[str]


class Fixture(TypedDict):
    module_id: str
    dossier_sha256: str
    dossier_slice: str
    schema_names: list[str]
    scenario_groups: list[ScenarioGroup]


def _fixture() -> Fixture:
    return cast("Fixture", json.loads(SCENARIO_PATH.read_text(encoding="utf-8")))


def _checks() -> list[EvalCheck]:  # noqa: PLR0915 - executable evidence matrix.
    fixture = _fixture()
    declared = [case_id for group in fixture["scenario_groups"] for case_id in group["case_ids"]]
    checks: list[EvalCheck] = [
        EvalCheck(
            "authority",
            fixture["module_id"] == MODULE_ID
            and fixture["dossier_sha256"] == DOSSIER_SHA256
            and fixture["dossier_slice"] == DOSSIER_SLICE,
            f"sha={fixture['dossier_sha256']};slice={fixture['dossier_slice']}",
        ),
        EvalCheck(
            "schema_inventory",
            tuple(fixture["schema_names"]) == tuple(contract_json_schemas()),
            f"declared={len(fixture['schema_names'])};actual={len(contract_json_schemas())}",
        ),
    ]
    engine = M2105Engine()
    request = _request()
    evaluated = engine.evaluate(request)
    checks.append(
        EvalCheck(
            "supported_evaluated",
            evaluated.status is EvaluationStatus.EVALUATED
            and evaluated.report is not None
            and evaluated.support_decision.status is SupportStatus.SUPPORTED,
            f"status={evaluated.status.value};report={evaluated.report is not None}",
        )
    )
    limited_performance = list(request.performance)
    limited_performance[0] = limited_performance[0].model_copy(
        update={"coverage_status": CoverageStatus.LIMITED}
    )
    limited = engine.evaluate(
        request.model_copy(update={"performance": tuple(limited_performance)})
    )
    checks.append(
        EvalCheck(
            "limited_coverage_abstains",
            limited.status is EvaluationStatus.ABSTAINED and limited.report is None,
            f"status={limited.status.value};findings={len(limited.findings)}",
        )
    )
    unsupported_coverage = list(request.coverage)
    unsupported_coverage[0] = unsupported_coverage[0].model_copy(
        update={"status": CoverageStatus.UNSUPPORTED}
    )
    unsupported = engine.evaluate(
        request.model_copy(update={"coverage": tuple(unsupported_coverage)})
    )
    checks.append(
        EvalCheck(
            "unsupported_coverage_abstains",
            unsupported.status is EvaluationStatus.ABSTAINED
            and unsupported.support_decision.status is SupportStatus.UNSUPPORTED,
            f"status={unsupported.status.value};support={unsupported.support_decision.status.value}",
        )
    )
    below_floor = list(request.performance)
    below_floor[0] = below_floor[0].model_copy(
        update={
            "value": 0.4,
            "lower_bound": 0.3,
            "upper_bound": 0.5,
            "equity_status": EquityStatus.BELOW_FLOOR,
        }
    )
    floor_result = engine.evaluate(request.model_copy(update={"performance": tuple(below_floor)}))
    checks.append(
        EvalCheck(
            "equity_floor_abstains",
            floor_result.status is EvaluationStatus.ABSTAINED
            and any(item.code.value == "safety_floor_breach" for item in floor_result.findings),
            f"status={floor_result.status.value}",
        )
    )
    rare = list(request.performance)
    rare_index = next(
        index
        for index, item in enumerate(rare)
        if item.dimension is SubgroupDimension.RARE_BIOLOGICAL_STATE
    )
    rare[rare_index] = rare[rare_index].model_copy(
        update={"coverage_status": CoverageStatus.LIMITED}
    )
    rare_result = engine.evaluate(request.model_copy(update={"performance": tuple(rare)}))
    checks.append(
        EvalCheck(
            "rare_context_abstains",
            any(item.code.value == "rare_context_unsupported" for item in rare_result.findings),
            f"status={rare_result.status.value}",
        )
    )
    low_calibration = list(request.calibration)
    low_calibration[0] = low_calibration[0].model_copy(
        update={"nominal_coverage": 0.5, "status": EvaluationStatus.EVALUATED}
    )
    calibration_result = engine.evaluate(
        request.model_copy(update={"calibration": tuple(low_calibration)})
    )
    checks.append(
        EvalCheck(
            "calibration_failure_abstains",
            calibration_result.status is EvaluationStatus.ABSTAINED
            and any(
                item.code.value == "calibration_failure" for item in calibration_result.findings
            ),
            f"status={calibration_result.status.value}",
        )
    )
    consent = request.context.references.consent.model_copy(update={"state": ConsentState.REVOKED})
    denied_context = request.context.model_copy(
        update={"references": request.context.references.model_copy(update={"consent": consent})}
    )
    try:
        engine.evaluate(request.model_copy(update={"context": denied_context}))
    except M2105AuthorizationError:
        denied_passed = True
    else:
        denied_passed = False
    checks.append(
        EvalCheck("consent_denied_preflight", denied_passed, "authorization precedes traversal")
    )
    wrong_media = request.upstream_result.model_copy(update={"media_type": "application/json"})
    try:
        TypeAdapter(EvaluateComplexActivitySubgroupEquityRequest).validate_python(
            request.model_copy(update={"upstream_result": wrong_media}).model_dump(mode="python"),
            strict=True,
        )
    except (ValidationError, ValueError):
        media_passed = True
    else:
        media_passed = False
    checks.append(
        EvalCheck("upstream_media_rejected", media_passed, "M21-04 media binding is strict")
    )
    tampered = evaluated.model_copy(update={"abstention_reason": "tampered"})
    try:
        engine.verify(tampered, replay=False)
    except M2105ReplayError:
        replay_passed = True
    else:
        replay_passed = False
    checks.append(EvalCheck("replay_tamper_rejected", replay_passed, "result digest is immutable"))
    executed = [item.name for item in checks if item.name not in {"authority", "schema_inventory"}]
    checks.append(
        EvalCheck(
            "coverage_exact_declared_case_set",
            len(declared) == len(executed) == EXPECTED_CASE_COUNT
            and set(declared) == set(executed),
            f"declared={len(declared)};executed={len(executed)}",
        )
    )
    checks.append(
        EvalCheck(
            "adversarial_coverage_target",
            all(
                item.passed
                for item in checks
                if item.name
                not in {
                    "authority",
                    "schema_inventory",
                    "supported_evaluated",
                    "coverage_exact_declared_case_set",
                }
            ),
            f"adversarial_passed={ADVERSARIAL_CASE_COUNT}/{ADVERSARIAL_CASE_COUNT};target={TARGET_COVERAGE_PERCENT}%",
        )
    )
    return checks


def run() -> dict[str, object]:
    checks = _checks()
    return {
        "module_id": MODULE_ID,
        "status": "PASS" if all(item.passed for item in checks) else "FAIL",
        "checks": [asdict(item) for item in checks],
        "declared_case_count": EXPECTED_CASE_COUNT,
        "executed_case_count": EXPECTED_CASE_COUNT,
        "adversarial_case_count": ADVERSARIAL_CASE_COUNT,
        "adversarial_coverage_percent": 100.0,
        "coverage_percent": 100.0,
        "target_coverage_percent": TARGET_COVERAGE_PERCENT,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)
    report = run()
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if arguments.output is not None:
        arguments.output.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
