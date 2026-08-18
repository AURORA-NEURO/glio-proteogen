"""Deterministic M13-07 evaluator over a frozen scenario matrix."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Final

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m13_07.factory import build_request
from glio_proteogen.contracts.m13_07 import ControlOutcome
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.modules.c11_protein_native_subtype import (
    m13_07_plausibility_adjudicator as m1307,
)

M1307PlausibilityEngine = m1307.M1307PlausibilityEngine
PlausibilityAuthorizationError = m1307.PlausibilityAuthorizationError
PlausibilityReplayError = m1307.PlausibilityReplayError

_FIXTURE = Path(__file__).parents[2] / "tests" / "fixtures" / "m13_07" / "scenarios.json"
_FIXTURE_SHA256: Final = "sha256:284c26a62ad62de735eb8de1497612dd1d98acb2bfd551796d80f3b0705e064c"


class _EvaluatorFixtureError(RuntimeError):
    def __init__(self, code: str) -> None:
        messages = {
            "digest": "M13-07 evaluator fixture digest mismatch",
            "cases": "M13-07 evaluator fixture cases are invalid",
            "case": "M13-07 evaluator case is invalid",
            "unknown": "unknown M13-07 evaluator case",
        }
        super().__init__(messages[code])


def _fixture() -> tuple[dict[str, object], str]:
    raw = _FIXTURE.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    return json.loads(raw), f"sha256:{digest}"


def _execute_case(engine: M1307PlausibilityEngine, kind: str) -> tuple[str, str]:
    if kind == "supported":
        result = engine.adjudicate(build_request())
        return result.status.value, result.support_decision.status.value
    if kind == "failed":
        result = engine.adjudicate(build_request(outcome=ControlOutcome.FAILED))
        return result.status.value, result.support_decision.status.value
    if kind == "not_evaluable":
        result = engine.adjudicate(build_request(outcome=ControlOutcome.NOT_EVALUABLE))
        return result.status.value, result.support_decision.status.value
    if kind == "conflict":
        result = engine.adjudicate(build_request(conflict=True))
        return result.status.value, result.support_decision.status.value
    if kind == "denied":
        engine.adjudicate(build_request(support=UpstreamDecisionState.REJECTED))
        return "unexpected_success", "none"
    if kind == "tamper":
        request = build_request()
        result = engine.adjudicate(request)
        engine.verify(request, result.model_copy(update={"result_id": "tampered"}))
        return "unexpected_success", "none"
    raise _EvaluatorFixtureError("unknown")


def run_evaluator() -> dict[str, object]:
    fixture, fixture_digest = _fixture()
    if fixture_digest != _FIXTURE_SHA256:
        raise _EvaluatorFixtureError("digest")
    cases = fixture["cases"]
    if not isinstance(cases, list):
        raise _EvaluatorFixtureError("cases")
    outcomes: list[dict[str, object]] = []
    engine = M1307PlausibilityEngine()
    for raw_case in cases:
        if not isinstance(raw_case, dict):
            raise _EvaluatorFixtureError("case")
        case_id = str(raw_case["id"])
        kind = str(raw_case["kind"])
        expected = str(raw_case["expected_status"])
        try:
            observed, support = _execute_case(engine, kind)
        except PlausibilityAuthorizationError:
            observed, support = "authorization_error", "none"
        except (PlausibilityReplayError, ValueError):
            observed, support = "replay_error", "none"
        passed = observed == expected and support == str(raw_case["expected_support"])
        outcomes.append(
            {
                "case_id": case_id,
                "expected_status": expected,
                "observed_status": observed,
                "expected_support": raw_case["expected_support"],
                "observed_support": support,
                "passed": passed,
            }
        )
    passed_count = sum(1 for item in outcomes if item["passed"])
    return {
        "module_id": fixture["module_id"],
        "operation": fixture["operation"],
        "fixture_version": fixture["fixture_version"],
        "fixture_digest": fixture_digest,
        "declared_cases": len(outcomes),
        "executed_cases": len(outcomes),
        "passed_cases": passed_count,
        "all_passed": passed_count == len(outcomes),
        "cases": outcomes,
    }


def main() -> int:
    report = run_evaluator()
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["run_evaluator"]
