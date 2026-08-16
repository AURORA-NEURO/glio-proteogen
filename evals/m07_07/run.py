"""Run the locked synthetic M07-07 evaluation matrix."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final, cast

from glio_proteogen.contracts.m07_07 import SelectiveCandidate
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c07_copy_number_dosage.m07_07_calibration_selective_prediction import (
    CalibrationAuthorizationError,
    M0707CalibrationEngine,
    M0707Service,
)

from .fixtures import request

_SCENARIOS: Final = Path(__file__).with_name("scenarios.json")


def _case(case_id: str) -> tuple[str, dict[str, object]]:  # noqa: C901, PLR0911
    engine = M0707CalibrationEngine()
    service = M0707Service(engine)
    if case_id == "calibrated_selection":
        result = service.execute(request())
        return result.status.value, {"estimate_count": len(result.estimates)}
    if case_id == "upstream_not_evaluable":
        result = service.execute(request(supported=False))
        return result.status.value, {"support_status": result.support_decision.status.value}
    if case_id == "missing_calibration_dimension":
        result = service.execute(request(include_all_dimensions=False))
        return result.status.value, {"review_required": result.human_review_required}
    if case_id == "withheld_consent":
        try:
            service.execute(request(consent_state=ConsentState.WITHHELD))
        except CalibrationAuthorizationError:
            return "authorization_error", {}
        raise AssertionError("withheld consent unexpectedly executed")  # noqa: TRY003
    if case_id == "no_candidate_passes":
        active_policy = request().policy
        strata = tuple(item.stratum_id for item in active_policy.strata)
        candidates = (
            SelectiveCandidate(
                feature_id="feature.ood",
                category="unknown",
                support_score=0.1,
                ood_score=0.9,
                calibration_error=0.9,
                stratum_ids=strata,
            ),
        )
        result = service.execute(request(candidates=candidates))
        return result.status.value, {"diagnostics": len(result.diagnostics)}
    if case_id == "replay_round_trip":
        active_request = request()
        result = service.execute(active_request)
        verified = service.verify_result(result.model_dump(mode="python"), active_request)
        return "verified", {"result_digest": verified.result_digest}
    if case_id == "tamper_replay":
        result = service.execute(request())
        tampered = result.model_dump(mode="python")
        tampered["result_digest"] = "sha256:" + "b" * 64
        try:
            service.verify_result(tampered)
        except ValueError:
            return "tamper_rejected", {}
        raise AssertionError("tampered digest unexpectedly verified")  # noqa: TRY003
    if case_id == "deterministic_reorder":
        active_request = request()
        reordered = active_request.model_copy(
            update={"candidates": tuple(reversed(active_request.candidates))}
        )
        first = service.execute(active_request)
        second = service.execute(reordered)
        return (
            "same_digest" if first.result_digest == second.result_digest else "different_digest",
            {},
        )
    raise KeyError(case_id)


def evaluate() -> dict[str, object]:
    """Execute every declared scenario exactly once and return a JSON report."""

    inventory = cast("dict[str, object]", json.loads(_SCENARIOS.read_text(encoding="utf-8")))
    declared = cast("list[dict[str, object]]", inventory["scenarios"])
    results: list[dict[str, object]] = []
    for scenario in declared:
        case_id = str(scenario["id"])
        observed, details = _case(case_id)
        expected = str(scenario["expected"])
        results.append(
            {
                "id": case_id,
                "expected": expected,
                "observed": observed,
                "details": details,
                "passed": observed == expected,
            }
        )
    passed = sum(1 for result in results if result["passed"])
    return {
        "module_id": inventory["module_id"],
        "dossier_sha256": inventory["dossier_sha256"],
        "authority_lines": inventory["authority_lines"],
        "abi_status": inventory["abi_status"],
        "declared": len(declared),
        "executed": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "status": "passed" if passed == len(results) else "failed",
        "results": results,
    }


def main() -> None:
    print(json.dumps(evaluate(), indent=2, sort_keys=True))  # noqa: T201


if __name__ == "__main__":
    main()


__all__ = ["evaluate", "main"]
