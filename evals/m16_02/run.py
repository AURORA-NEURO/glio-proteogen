"""Run the locked synthetic M16-02 alignment reconciliation matrix."""

# CLI evidence runner intentionally prints its machine-readable report.
# ruff: noqa: E501, PLR2004, T201, TRY003

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

from tests.contract.test_m16_02_deep import _request

from glio_proteogen.contracts.m16_02 import (
    AlignmentDecisionStatus,
    DiscrepancyResolutionStatus,
)
from glio_proteogen.contracts.m16_02.canonical import result_payload_digest
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.modules.c16_kinophos_object_consumer.m16_02_cross_source_alignment_reconciliation import (
    M1602AlignmentEngine,
    M1602AuthorizationError,
)

MODULE_ID = "GLIO-PROTEOGEN-M16-02"
SCENARIO_PATH = Path(__file__).parents[2] / "tests" / "fixtures" / "m16_02" / "scenarios.json"
EXPECTED_CASE_IDS = (
    "aligned_reconciled",
    "warning_review_required",
    "critical_conflict_review",
    "resolved_conflict_reconciled",
    "unsupported_abstention",
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
    """Execute every locked fixture case and return JSON-safe evidence."""

    fixture = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    case_ids = tuple(item["case_id"] for item in fixture["cases"])
    if case_ids != EXPECTED_CASE_IDS:
        raise ValueError("M16-02 fixture case IDs are not locked")
    engine = M1602AlignmentEngine()
    checks: list[EvalCheck] = []

    aligned = engine.reconcile(_request())
    checks.append(
        EvalCheck(
            "aligned_reconciled",
            aligned.status is AlignmentDecisionStatus.RECONCILED
            and aligned.bundle is not None
            and not aligned.bundle.discrepancies,
            aligned.status.value,
        )
    )
    warning = engine.reconcile(_request(label="warning"))
    checks.append(
        EvalCheck(
            "warning_review_required",
            warning.status is AlignmentDecisionStatus.REVIEW_REQUIRED
            and warning.bundle is not None
            and warning.human_review_required,
            warning.status.value,
        )
    )
    critical = engine.reconcile(_request(label="critical"))
    checks.append(
        EvalCheck(
            "critical_conflict_review",
            critical.status is AlignmentDecisionStatus.REVIEW_REQUIRED
            and critical.bundle is not None
            and critical.bundle.discrepancies[0].resolution_status
            is DiscrepancyResolutionStatus.OPEN,
            critical.status.value,
        )
    )
    resolved = engine.reconcile(_request(label="resolved"))
    checks.append(
        EvalCheck(
            "resolved_conflict_reconciled",
            resolved.status is AlignmentDecisionStatus.RECONCILED
            and resolved.bundle is not None
            and resolved.bundle.discrepancies[0].resolution_status
            is DiscrepancyResolutionStatus.RESOLVED,
            resolved.status.value,
        )
    )
    unsupported = engine.reconcile(_request(label="unsupported"))
    checks.append(
        EvalCheck(
            "unsupported_abstention",
            unsupported.status is AlignmentDecisionStatus.ABSTAINED
            and unsupported.bundle is None
            and unsupported.abstention_reason is not None,
            unsupported.status.value,
        )
    )
    prohibited = engine.reconcile(_request(label="kinase"))
    checks.append(
        EvalCheck(
            "prohibited_boundary_abstention",
            prohibited.status is AlignmentDecisionStatus.ABSTAINED
            and any(item.value == "upstream_unsupported" for item in prohibited.findings),
            prohibited.status.value,
        )
    )

    replay = engine.reconcile(_request())
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
        engine.reconcile(_request(accepted=False))
    except M1602AuthorizationError:
        denied = True
    checks.append(EvalCheck("authorization_gate", denied, "denied controls rejected"))

    first = engine.reconcile(_request())
    second = engine.reconcile(_request())
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
        "fixture": "tests/fixtures/m16_02/scenarios.json",
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
