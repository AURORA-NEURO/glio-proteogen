"""Run the locked synthetic M15-01 biological hypothesis registry matrix."""

# CLI evidence runner intentionally prints its machine-readable report.
# ruff: noqa: E501, T201, TRY003

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

from tests.modules.c15_longitudinal_recurrence.test_m15_01_engine import _request

from glio_proteogen.contracts.m15_01 import HypothesisStatus
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.modules.c15_longitudinal_recurrence.m15_01_biological_hypothesis_registry import (
    M1501AuthorizationError,
    M1501HypothesisRegistry,
)

MODULE_ID = "GLIO-PROTEOGEN-M15-01"
EXPECTED_CONTROL_COUNT = 7
EXPECTED_PROBABILITY = 0.9
SCENARIO_PATH = Path(__file__).parents[2] / "tests" / "fixtures" / "m15_01" / "scenarios.json"
EXPECTED_CASE_IDS = (
    "all_hypotheses_supported",
    "unsupported_tier_abstention",
    "failed_falsification_abstention",
    "prohibited_statement_abstention",
    "conflicted_hypothesis_abstention",
    "replay_and_tamper",
    "authorization_gate",
    "deterministic_reconstruction",
    "provenance_uncertainty_complete",
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
        raise ValueError("M15-01 fixture case IDs are not locked")
    engine = M1501HypothesisRegistry()
    checks: list[EvalCheck] = []

    supported = engine.infer(_request())
    checks.append(
        EvalCheck(
            "all_hypotheses_supported",
            supported.status is HypothesisStatus.SUPPORTED,
            supported.status.value,
        )
    )
    for name, request in (
        ("unsupported_tier_abstention", _request(tier_label="unsupported")),
        ("failed_falsification_abstention", _request(rule_failure="Evidence is absent.")),
        (
            "prohibited_statement_abstention",
            _request(statement="Treatment response should be recommended."),
        ),
        ("conflicted_hypothesis_abstention", _request(status=HypothesisStatus.CONFLICTED)),
    ):
        result = engine.infer(request)
        checks.append(
            EvalCheck(name, result.status is HypothesisStatus.ABSTAINED, result.status.value)
        )

    replay = engine.infer(_request())
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
        engine.infer(_request(accepted=False))
    except M1501AuthorizationError:
        denied = True
    checks.append(EvalCheck("authorization_gate", denied, "denied controls rejected"))

    first = engine.infer(_request())
    second = engine.infer(_request())
    checks.append(
        EvalCheck("deterministic_reconstruction", first == second, "byte-equivalent result")
    )
    checks.append(
        EvalCheck(
            "provenance_uncertainty_complete",
            len(first.provenance.control_decisions) == EXPECTED_CONTROL_COUNT
            and first.uncertainty.measurement.probability is None
            and len(first.uncertainty.sensitivity_notes) >= 1,
            "seven controls and seven uncertainty dimensions are explicit",
        )
    )

    passed = sum(item.passed for item in checks)
    return {
        "module_id": MODULE_ID,
        "fixture": str(SCENARIO_PATH),
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
