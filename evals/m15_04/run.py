"""Run the locked synthetic M15-04 mechanism inference matrix."""

# CLI evidence runner intentionally prints its machine-readable report.
# ruff: noqa: E501, PLR2004, T201, TRY003

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from tests.modules.c15_longitudinal_recurrence.test_m15_04_engine import _request

from glio_proteogen.contracts.m15_04 import MechanismEstimateKind, MechanismInferenceStatus
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.modules.c15_longitudinal_recurrence.m15_04_network_state_mechanism_inference import (
    M1504AuthorizationError,
    M1504MechanismInference,
)

MODULE_ID = "GLIO-PROTEOGEN-M15-04"
SCENARIO_PATH = Path(__file__).parents[2] / "tests" / "fixtures" / "m15_04" / "scenarios.json"
EXPECTED_CASE_IDS = (
    "posterior_positive_control",
    "state_positive_control",
    "unsupported_abstention",
    "negative_control_rejection",
    "prohibited_boundary_abstention",
    "replay_and_tamper",
    "authorization_gate",
    "deterministic_reconstruction",
    "counter_evidence_uncertainty_complete",
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
        raise ValueError("M15-04 fixture case IDs are not locked")
    engine = M1504MechanismInference()
    checks: list[EvalCheck] = []

    posterior = engine.infer(_request())
    checks.append(
        EvalCheck(
            "posterior_positive_control",
            posterior.status is MechanismInferenceStatus.INFERRED
            and posterior.estimates[0].kind is MechanismEstimateKind.POSTERIOR,
            posterior.status.value,
        )
    )
    state = engine.infer(_request(method="state_space_proteoform_model"))
    checks.append(
        EvalCheck(
            "state_positive_control",
            state.status is MechanismInferenceStatus.INFERRED
            and state.estimates[0].kind is MechanismEstimateKind.STATE,
            state.status.value,
        )
    )
    for name, request in (
        ("unsupported_abstention", _request(method="unsupported_baseline")),
        ("negative_control_rejection", _request(method="negative_control_gate")),
        ("prohibited_boundary_abstention", _request(method="kinase_activity_model")),
    ):
        result = engine.infer(request)
        checks.append(
            EvalCheck(
                name, result.status is MechanismInferenceStatus.ABSTAINED, result.status.value
            )
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
    except M1504AuthorizationError:
        denied = True
    checks.append(EvalCheck("authorization_gate", denied, "denied controls rejected"))

    first = engine.infer(_request())
    second = engine.infer(_request())
    checks.append(
        EvalCheck("deterministic_reconstruction", first == second, "byte-equivalent result")
    )
    checks.append(
        EvalCheck(
            "counter_evidence_uncertainty_complete",
            first.estimates[0].counter_evidence[0].role == "counter_evidence"
            and len(first.provenance.control_decisions) == 7
            and first.uncertainty.measurement.probability == 0.9,
            "counter-evidence, seven controls, and uncertainty are explicit",
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
