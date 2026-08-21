"""Run the locked synthetic M17-06 adjudication matrix."""

# CLI evidence runner intentionally prints machine-readable JSON.
# ruff: noqa: PLR2004, T201, TRY003

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from tests.contract.test_m17_06_deep import _assignment, _entry, _request

from glio_proteogen.contracts.m17_06 import QueueEntryState, QueueResultStatus, ReviewDecision
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m17_06_reviewer_discrepancy_adjudication as m1706,
)

MODULE_ID = "GLIO-PROTEOGEN-M17-06"
SCENARIO_PATH = Path(__file__).parents[2] / "tests" / "fixtures" / "m17_06" / "scenarios.json"
EXPECTED_CASE_IDS = (
    "resolved_queue_recorded",
    "unresolved_review_abstention",
    "escalated_abstention",
    "unsupported_abstention",
    "prohibited_scope_abstention",
    "replay_and_tamper",
    "authorization_gate",
    "deterministic_reconstruction",
    "uncertainty_provenance_complete",
    "complete_blinded_assignment",
)


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def evaluate() -> dict[str, object]:
    """Execute every locked fixture case and return JSON-safe evidence."""

    fixture = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    case_ids = tuple(item["case_id"] for item in fixture["cases"])
    if case_ids != EXPECTED_CASE_IDS:
        raise ValueError("M17-06 fixture case IDs are not locked")
    engine = m1706.M1706AdjudicationEngine()
    checks: list[EvalCheck] = []

    resolved = engine.export(_request())
    checks.append(
        EvalCheck(
            "resolved_queue_recorded",
            resolved.status is QueueResultStatus.RECORDED and resolved.record is not None,
            resolved.status.value,
        )
    )
    review_request = _request(
        entries=(_entry(state=QueueEntryState.IN_REVIEW),),
        assignments=(_assignment(decision=ReviewDecision.DEFER),),
    )
    review = engine.export(review_request)
    checks.append(
        EvalCheck(
            "unresolved_review_abstention",
            review.status is QueueResultStatus.ABSTAINED
            and review.record is None
            and review.support_decision.status.value == "review_required",
            review.status.value,
        )
    )
    escalated = engine.export(_request(entries=(_entry(state=QueueEntryState.ESCALATED),)))
    checks.append(
        EvalCheck(
            "escalated_abstention",
            escalated.status is QueueResultStatus.ABSTAINED
            and escalated.record is None
            and any(item.code.value == "critical_unresolved" for item in escalated.findings),
            escalated.status.value,
        )
    )
    unsupported = engine.export(
        _request(entries=(_entry().model_copy(update={"description": "unsupported source"}),))
    )
    checks.append(
        EvalCheck(
            "unsupported_abstention",
            unsupported.status is QueueResultStatus.ABSTAINED
            and unsupported.support_decision.status.value == "unsupported",
            unsupported.status.value,
        )
    )
    prohibited = engine.export(
        _request(entries=(_entry().model_copy(update={"description": "kinase activity claim"}),))
    )
    checks.append(
        EvalCheck(
            "prohibited_scope_abstention",
            prohibited.status is QueueResultStatus.ABSTAINED and prohibited.record is None,
            prohibited.status.value,
        )
    )
    replay = engine.export(_request())
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
        engine.export(_request().model_copy(update={"context": None}))
    except m1706.M1706AuthorizationError:
        denied = True
    checks.append(EvalCheck("authorization_gate", denied, "invalid controls rejected"))
    first = engine.export(_request())
    second = engine.export(_request())
    checks.append(
        EvalCheck("deterministic_reconstruction", first == second, "byte-equivalent result")
    )
    checks.append(
        EvalCheck(
            "uncertainty_provenance_complete",
            first.uncertainty.transport.probability is None
            and len(first.provenance.control_decisions) == 7,
            "seven uncertainty dimensions and seven controls are explicit",
        )
    )
    checks.append(
        EvalCheck(
            "complete_blinded_assignment",
            first.record is not None
            and len(first.record.assignments) == len(first.record.entries)
            and all(item.blinded for item in first.record.assignments),
            "every queue entry has a blinded assignment",
        )
    )
    passed = sum(item.passed for item in checks)
    return {
        "module_id": MODULE_ID,
        "fixture": "tests/fixtures/m17_06/scenarios.json",
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
