"""Executable M24-02 evaluator matrix."""

from __future__ import annotations

import json
from typing import Any

from glio_proteogen.contracts.m24_02 import FixtureKind, GenerationStatus
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.modules.c21_reference_material import (
    m24_02_synthetic_truth_simulation_generator as m2402,
)

from .fixture import build_request, denied_request


def run_evaluator() -> dict[str, Any]:
    expected_case_count = 10
    expected_control_count = 7
    service = m2402.M2402Service()
    request = build_request()
    result = service.generate(request)
    repeated = service.generate(request)
    checks: dict[str, bool] = {
        "generated": result.status is GenerationStatus.GENERATED,
        "corpus_present": result.corpus is not None and result.manifest is not None,
        "declared_case_count": (
            result.corpus is not None and len(result.corpus.cases) == expected_case_count
        ),
        "all_fixture_kinds": (
            result.corpus is not None
            and {case.fixture_kind for case in result.corpus.cases} == set(FixtureKind)
        ),
        "analytic_recovery": (
            result.corpus is not None
            and all(case.analytically_recoverable for case in result.corpus.cases)
        ),
        "deterministic_repeat": result.result_digest == repeated.result_digest,
        "replay_verified": service.verify_replay(result).result_digest == result.result_digest,
        "seven_control_provenance": (
            len(result.provenance.control_decisions) == expected_control_count
        ),
        "parent_boundary": (
            result.emits_parent is False and result.parent_target == "biomarker panel"
        ),
    }
    try:
        service.generate(denied_request())
    except m2402.M2402AuthorizationError:
        checks["denied_fail_closed"] = True
    else:
        checks["denied_fail_closed"] = False
    tampered = result.model_copy(update={"result_digest": sha256_digest("tampered")})
    try:
        service.verify_replay(tampered)
    except m2402.M2402ReplayError:
        checks["tamper_rejected"] = True
    else:
        checks["tamper_rejected"] = False
    return {
        "adversarial_case_count": len(checks),
        "adversarial_passed_count": sum(checks.values()),
        "module_id": "GLIO-PROTEOGEN-M24-02",
        "checks": checks,
        "fixture_digest": sha256_digest(request),
        "fixture_result_digest": result.result_digest,
        "scenario_count": len(checks),
        "passed": all(checks.values()),
    }


def main() -> int:
    report = run_evaluator()
    print(json.dumps(report, sort_keys=True))  # noqa: T201
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
