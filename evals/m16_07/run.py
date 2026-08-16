"""Run the locked synthetic M16-07 downstream export matrix."""

# CLI evidence runner intentionally prints machine-readable JSON.
# ruff: noqa: PLR2004, T201, TRY003

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from tests.modules.c16_kinophos_object_consumer.test_m16_07_engine import _request

from glio_proteogen.contracts.m16_07 import (
    CompatibilityStatus,
    ExportStatus,
    FieldSupportStatus,
)
from glio_proteogen.contracts.m16_07.canonical import result_payload_digest
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.modules.c16_kinophos_object_consumer.m16_07_downstream_typed_export import (
    M1607AuthorizationError,
    M1607ExportEngine,
)

MODULE_ID = "GLIO-PROTEOGEN-M16-07"
SCENARIO_PATH = Path(__file__).parents[2] / "tests" / "fixtures" / "m16_07" / "scenarios.json"
EXPECTED_CASE_IDS = (
    "signed_export",
    "warning_review_abstention",
    "ownership_mismatch",
    "unsupported_abstention",
    "prohibited_boundary_abstention",
    "replay_and_tamper",
    "authorization_gate",
    "deterministic_reconstruction",
    "uncertainty_provenance_complete",
    "compatibility_support_closure",
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
        raise ValueError("M16-07 fixture case IDs are not locked")
    engine = M1607ExportEngine()
    checks: list[EvalCheck] = []

    signed = engine.export(_request())
    checks.append(
        EvalCheck(
            "signed_export",
            signed.status is ExportStatus.SIGNED
            and signed.downstream_contract is not None
            and signed.compatibility_report.status is CompatibilityStatus.COMPATIBLE,
            signed.status.value,
        )
    )
    warning = engine.export(_request(label="warning"))
    checks.append(
        EvalCheck(
            "warning_review_abstention",
            warning.status is ExportStatus.ABSTAINED
            and warning.compatibility_report.status is CompatibilityStatus.REVIEW_REQUIRED
            and warning.human_review_required,
            warning.status.value,
        )
    )
    owner = engine.export(_request(owner="owner.other"))
    checks.append(
        EvalCheck(
            "ownership_mismatch",
            owner.status is ExportStatus.ABSTAINED
            and owner.compatibility_report.status is CompatibilityStatus.INCOMPATIBLE,
            owner.status.value,
        )
    )
    unsupported = engine.export(_request(label="unsupported"))
    checks.append(
        EvalCheck(
            "unsupported_abstention",
            unsupported.status is ExportStatus.ABSTAINED
            and unsupported.downstream_contract is None
            and unsupported.abstention_reason is not None,
            unsupported.status.value,
        )
    )
    prohibited = engine.export(_request(label="kinase"))
    checks.append(
        EvalCheck(
            "prohibited_boundary_abstention",
            prohibited.status is ExportStatus.ABSTAINED
            and prohibited.downstream_contract is None
            and prohibited.human_review_required,
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
        engine.export(_request(accepted=False))
    except M1607AuthorizationError:
        denied = True
    checks.append(EvalCheck("authorization_gate", denied, "denied controls rejected"))
    first = engine.export(_request())
    second = engine.export(_request())
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
    limited = engine.export(_request(support_status=FieldSupportStatus.LIMITED))
    checks.append(
        EvalCheck(
            "compatibility_support_closure",
            limited.status is ExportStatus.ABSTAINED
            and limited.compatibility_report.status is CompatibilityStatus.INCOMPATIBLE
            and limited.support_decision.status.value == "unsupported",
            limited.status.value,
        )
    )
    passed = sum(item.passed for item in checks)
    return {
        "module_id": MODULE_ID,
        "fixture": "tests/fixtures/m16_07/scenarios.json",
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
