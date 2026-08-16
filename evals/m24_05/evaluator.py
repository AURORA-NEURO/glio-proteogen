"""Executable M24-05 evaluator matrix."""

from __future__ import annotations

import json
from typing import Any

from glio_proteogen.contracts.m24_05 import EvaluationStatus
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.modules.c21_reference_material import (
    m24_05_subgroup_equity_evaluator as m2405,
)

from .fixture import (
    build_request,
    calibration_abstained_request,
    denied_request,
    floor_request,
    rare_limited_request,
    unsupported_request,
)

EXPECTED_DIMENSIONS = 8
CONTROL_COUNT = 7


def run_evaluator() -> dict[str, Any]:
    service = m2405.M2405Service()
    request = build_request()
    result = service.evaluate(request)
    repeated = service.evaluate(request)
    checks: dict[str, bool] = {
        "evaluated": result.status is EvaluationStatus.EVALUATED,
        "report_present": result.report is not None,
        "all_dimensions": (
            result.report is not None
            and len(result.report.performance) == EXPECTED_DIMENSIONS
            and len(result.report.calibration) == EXPECTED_DIMENSIONS
            and len(result.report.coverage) == EXPECTED_DIMENSIONS
        ),
        "deterministic_repeat": result.result_digest == repeated.result_digest,
        "replay_verified": service.verify_replay(result).result_digest == result.result_digest,
        "floor_abstention": service.evaluate(floor_request()).status is EvaluationStatus.ABSTAINED,
        "unsupported_abstention": service.evaluate(unsupported_request()).status
        is EvaluationStatus.ABSTAINED,
        "rare_context_abstention": service.evaluate(rare_limited_request()).status
        is EvaluationStatus.ABSTAINED,
        "calibration_abstention": service.evaluate(calibration_abstained_request()).status
        is EvaluationStatus.ABSTAINED,
        "seven_control_provenance": len(result.provenance.control_decisions) == CONTROL_COUNT,
        "parent_boundary": result.emits_parent is False
        and result.parent_target == "biomarker panel",
    }
    try:
        service.evaluate(denied_request())
    except m2405.M2405AuthorizationError:
        checks["denied_fail_closed"] = True
    else:
        checks["denied_fail_closed"] = False
    tampered = result.model_copy(update={"result_digest": sha256_digest("tampered")})
    try:
        service.verify_replay(tampered)
    except m2405.M2405ReplayError:
        checks["tamper_rejected"] = True
    else:
        checks["tamper_rejected"] = False
    return {
        "adversarial_case_count": len(checks),
        "adversarial_passed_count": sum(checks.values()),
        "checks": checks,
        "dossier_sha256": "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181",
        "dossier_slice": "GLIO-PROTEOGEN_240_Module_Dossier.md:8492-8532",
        "fixture_digest": sha256_digest(request),
        "fixture_result_digest": result.result_digest,
        "module_id": "GLIO-PROTEOGEN-M24-05",
        "passed": all(checks.values()),
        "scenario_count": len(checks),
    }


def main() -> int:
    report = run_evaluator()
    print(json.dumps(report, sort_keys=True))  # noqa: T201
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
