"""Run the locked synthetic M15-07 plausibility adjudication matrix."""

# CLI evidence runner intentionally prints its machine-readable report.
# ruff: noqa: E501, PLR2004, T201, TRY003

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from tests.modules.c15_longitudinal_recurrence.test_m15_07_engine import _request

from glio_proteogen.contracts.m15_07 import (
    ControlOutcome,
    PlausibilityAdjudicationStatus,
)
from glio_proteogen.contracts.m15_07.canonical import result_payload_digest
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.modules.c15_longitudinal_recurrence.m15_07_plausibility_negative_control_adjudicator import (
    M1507AuthorizationError,
    M1507PlausibilityAdjudicator,
)

MODULE_ID = "GLIO-PROTEOGEN-M15-07"
SCENARIO_PATH = Path(__file__).parents[2] / "tests" / "fixtures" / "m15_07" / "scenarios.json"
EXPECTED_CASE_IDS = (
    "positive_control_adjudicated",
    "negative_control_rejection",
    "unsupported_abstention",
    "unresolved_conflict_visible",
    "prohibited_boundary_abstention",
    "replay_and_tamper",
    "authorization_gate",
    "deterministic_reconstruction",
    "uncertainty_provenance_complete",
)


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def evaluate() -> dict[str, object]:
    """Execute every fixture case and return a JSON-safe evidence report."""

    fixture = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    case_ids = tuple(item["case_id"] for item in fixture["cases"])
    if case_ids != EXPECTED_CASE_IDS:
        raise ValueError("M15-07 fixture case IDs are not locked")
    engine = M1507PlausibilityAdjudicator()
    checks: list[EvalCheck] = []

    positive = engine.adjudicate(_request())
    checks.append(
        EvalCheck(
            "positive_control_adjudicated",
            positive.status is PlausibilityAdjudicationStatus.ADJUDICATED
            and positive.grade is not None
            and all(item.outcome is ControlOutcome.PASSED for item in positive.evaluations),
            positive.status.value,
        )
    )
    for name, request, expected in (
        ("negative_control_rejection", _request("negative_control_gate"), ControlOutcome.FAILED),
        ("unsupported_abstention", _request("unsupported_input"), ControlOutcome.NOT_EVALUABLE),
    ):
        result = engine.adjudicate(request)
        checks.append(
            EvalCheck(
                name,
                result.status is PlausibilityAdjudicationStatus.ABSTAINED
                and any(item.outcome is expected for item in result.evaluations),
                result.status.value,
            )
        )
    conflict = engine.adjudicate(_request("unresolved_conflict"))
    checks.append(
        EvalCheck(
            "unresolved_conflict_visible",
            conflict.status is PlausibilityAdjudicationStatus.ABSTAINED
            and len(conflict.conflicts) == 1
            and conflict.human_review_required,
            "conflict preserved; review required",
        )
    )
    prohibited = engine.adjudicate(_request("kinase_activity"))
    checks.append(
        EvalCheck(
            "prohibited_boundary_abstention",
            prohibited.status is PlausibilityAdjudicationStatus.ABSTAINED
            and any(item.code.value == "upstream_unsupported" for item in prohibited.findings),
            prohibited.status.value,
        )
    )

    replay = engine.adjudicate(_request())
    tamper_rejected = False
    try:
        engine.verify(replay.model_copy(update={"result_digest": sha256_digest("tampered")}))
    except ValueError:
        tamper_rejected = True
    checks.append(
        EvalCheck(
            "replay_and_tamper",
            engine.verify(replay) == replay and tamper_rejected,
            "replay verified; tamper rejected",
        )
    )

    denied = False
    try:
        engine.adjudicate(_request("sensitivity", accepted=False))
    except M1507AuthorizationError:
        denied = True
    checks.append(EvalCheck("authorization_gate", denied, "denied controls rejected"))

    first = engine.adjudicate(_request())
    second = engine.adjudicate(_request())
    checks.append(
        EvalCheck("deterministic_reconstruction", first == second, "byte-equivalent result")
    )
    checks.append(
        EvalCheck(
            "uncertainty_provenance_complete",
            first.uncertainty.measurement.probability == 0.9
            and len(first.provenance.control_decisions) == 7
            and first.result_digest == result_payload_digest(first),
            "seven uncertainty dimensions, controls, and digest are explicit",
        )
    )

    passed = sum(item.passed for item in checks)
    return {
        "module_id": MODULE_ID,
        "fixture": "tests/fixtures/m15_07/scenarios.json",
        "fixture_digest": sha256_digest(fixture),
        "declared_cases": len(case_ids),
        "executed_cases": len(checks),
        "passed_cases": passed,
        "total_cases": len(checks),
        "passed": passed == len(checks),
        "checks": [asdict(item) for item in checks],
    }


def main() -> int:
    argparse.ArgumentParser().parse_args()
    report = evaluate()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
