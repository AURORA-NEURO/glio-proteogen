"""Run the locked synthetic M17-02 alignment matrix."""

# CLI evidence runner intentionally prints machine-readable JSON.
# ruff: noqa: PLR2004, T201, TRY003

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from tests.contract.test_m17_02_deep import _observation, _request

from glio_proteogen.contracts.m17_02 import AlignmentResultStatus, result_payload_digest
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m17_02_cross_source_alignment_reconciliation as m1702,
)

MODULE_ID = "GLIO-PROTEOGEN-M17-02"
SCENARIO_PATH = Path(__file__).parents[2] / "tests" / "fixtures" / "m17_02" / "scenarios.json"
EXPECTED_CASE_IDS = (
    "reconciled_alignment",
    "sample_conflict_abstention",
    "unsupported_abstention",
    "prohibited_scope_abstention",
    "review_required_status",
    "replay_and_tamper",
    "authorization_gate",
    "deterministic_reconstruction",
    "uncertainty_provenance_complete",
    "all_axis_alignment",
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
        raise ValueError("M17-02 fixture case IDs are not locked")
    engine = m1702.M1702AlignmentEngine()
    checks: list[EvalCheck] = []

    aligned = engine.export(_request())
    checks.append(
        EvalCheck(
            "reconciled_alignment",
            aligned.status is AlignmentResultStatus.RECONCILED
            and aligned.aligned_bundle is not None
            and not aligned.discrepancy_map,
            aligned.status.value,
        )
    )
    conflict_request = _request().model_copy(
        update={
            "observations": (
                _observation("observation.a"),
                _observation("observation.b").model_copy(update={"sample_id": "sample.002"}),
            )
        }
    )
    conflicted = engine.export(conflict_request)
    checks.append(
        EvalCheck(
            "sample_conflict_abstention",
            conflicted.status is AlignmentResultStatus.ABSTAINED
            and len(conflicted.discrepancy_map) == 1
            and conflicted.human_review_required,
            conflicted.status.value,
        )
    )
    unsupported = engine.export(
        _request().model_copy(
            update={
                "observations": (
                    _observation("observation.a").model_copy(update={"analyte": "unsupported"}),
                    _observation("observation.b"),
                )
            }
        )
    )
    checks.append(
        EvalCheck(
            "unsupported_abstention",
            unsupported.status is AlignmentResultStatus.ABSTAINED
            and unsupported.aligned_bundle is None
            and unsupported.support_decision.status.value == "unsupported",
            unsupported.status.value,
        )
    )
    prohibited = engine.export(
        _request().model_copy(
            update={
                "observations": (
                    _observation("observation.a").model_copy(update={"analyte": "kinase"}),
                    _observation("observation.b"),
                )
            }
        )
    )
    checks.append(
        EvalCheck(
            "prohibited_scope_abstention",
            prohibited.status is AlignmentResultStatus.ABSTAINED
            and prohibited.aligned_bundle is None,
            prohibited.status.value,
        )
    )
    checks.append(
        EvalCheck(
            "review_required_status",
            conflicted.support_decision.status.value == "review_required"
            and conflicted.discrepancy_map[0].review_required,
            "discrepancy preserved for review",
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
    except m1702.M1702AuthorizationError:
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
            first.uncertainty.transport.probability == 0.9
            and len(first.provenance.control_decisions) == 7
            and first.result_digest == result_payload_digest(first),
            "seven uncertainty dimensions, controls, and digest are explicit",
        )
    )
    checks.append(
        EvalCheck(
            "all_axis_alignment",
            first.aligned_bundle is not None
            and first.aligned_bundle.alignment_status.value == "aligned"
            and len(first.aligned_bundle.observations) == 2,
            "all seven axes resolved",
        )
    )
    passed = sum(item.passed for item in checks)
    return {
        "module_id": MODULE_ID,
        "fixture": "tests/fixtures/m17_02/scenarios.json",
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
