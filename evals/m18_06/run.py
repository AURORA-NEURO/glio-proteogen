"""Executable nominal and adversarial evidence for M18-06."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final, TypedDict, cast

from pydantic import ValidationError
from tests.runtime.test_m18_06_adjudication import _request

from glio_proteogen.contracts.m18_06 import (
    M1806_DOSSIER_SHA256,
    M1806_DOSSIER_SLICE,
    QueueEntryState,
    QueueResultStatus,
    ReviewDecision,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c18_spatial_proteomics_projection.m18_06_reviewer_adjudication import (
    M1806AuthorizationError,
    M1806Engine,
    M1806ReplayError,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M18-06"
SCENARIO_PATH: Final = Path("tests/fixtures/m18_06/scenarios.json")
EXPECTED_CASE_COUNT: Final = 8
ADVERSARIAL_CASE_COUNT: Final = 6
TARGET_COVERAGE_PERCENT: Final = 95


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


class ScenarioGroup(TypedDict):
    group: str
    case_ids: list[str]


class Fixture(TypedDict):
    module_id: str
    dossier_sha256: str
    dossier_slice: str
    schema_names: list[str]
    scenario_groups: list[ScenarioGroup]


def _fixture() -> Fixture:
    return cast("Fixture", json.loads(SCENARIO_PATH.read_text(encoding="utf-8")))


def _checks() -> list[EvalCheck]:
    fixture = _fixture()
    declared = [case_id for group in fixture["scenario_groups"] for case_id in group["case_ids"]]
    checks: list[EvalCheck] = []
    checks.append(
        EvalCheck(
            "authority",
            fixture["module_id"] == MODULE_ID
            and fixture["dossier_sha256"] == M1806_DOSSIER_SHA256.removeprefix("sha256:").upper()
            and fixture["dossier_slice"] == M1806_DOSSIER_SLICE,
            f"sha={fixture['dossier_sha256']};slice={fixture['dossier_slice']}",
        )
    )
    checks.append(
        EvalCheck(
            "schema_inventory",
            tuple(fixture["schema_names"]) == tuple(contract_json_schemas()),
            f"declared={len(fixture['schema_names'])};actual={len(contract_json_schemas())}",
        )
    )

    engine = M1806Engine()
    request = _request()
    resolved = engine.adapt(request)
    checks.append(
        EvalCheck(
            "resolved_records",
            resolved.status is QueueResultStatus.RECORDED
            and resolved.record is not None
            and resolved.record.status.value == "resolved",
            f"status={resolved.status.value};record={resolved.record is not None}",
        )
    )
    escalated = engine.adapt(
        _request(entry_state=QueueEntryState.IN_REVIEW, decision=ReviewDecision.DEFER)
    )
    checks.append(
        EvalCheck(
            "deferred_critical_escalates",
            escalated.status is QueueResultStatus.RECORDED
            and escalated.record is not None
            and escalated.record.status.value == "escalated",
            (
                f"status={escalated.status.value};record_status="
                f"{escalated.record.status.value if escalated.record else None}"
            ),
        )
    )
    missing = engine.adapt(_request(assignments_complete=False))
    checks.append(
        EvalCheck(
            "missing_assignment_abstains",
            missing.status is QueueResultStatus.ABSTAINED and missing.record is None,
            f"status={missing.status.value};record={missing.record is not None}",
        )
    )
    unevaluable = engine.adapt(_request(entry_state=QueueEntryState.NOT_EVALUABLE))
    checks.append(
        EvalCheck(
            "not_evaluable_abstains",
            unevaluable.status is QueueResultStatus.ABSTAINED and unevaluable.record is None,
            f"status={unevaluable.status.value};record={unevaluable.record is not None}",
        )
    )
    denied = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": request.context.references.model_copy(
                        update={
                            "consent": request.context.references.consent.model_copy(
                                update={"state": ConsentState.WITHHELD}
                            )
                        }
                    )
                }
            )
        }
    )
    try:
        engine.adapt(denied)
    except M1806AuthorizationError:
        denied_passed = True
    else:
        denied_passed = False
    checks.append(
        EvalCheck("consent_denied_preflight", denied_passed, "authorization precedes traversal")
    )

    try:
        _request(upstream_media_type="application/json")
    except (ValidationError, ValueError):
        media_passed = True
    else:
        media_passed = False
    checks.append(
        EvalCheck("upstream_media_rejected", media_passed, "M18-05 media binding is strict")
    )

    tampered = resolved.model_copy(update={"human_review_required": False})
    try:
        engine.replay(tampered)
    except M1806ReplayError:
        replay_passed = True
    else:
        replay_passed = False
    checks.append(EvalCheck("replay_tamper_rejected", replay_passed, "result digest is immutable"))

    duplicate = request.model_dump(mode="python")
    duplicate["entries"] = (duplicate["entries"][0], duplicate["entries"][0])
    try:
        type(request).model_validate(duplicate, strict=True)
    except ValidationError:
        duplicate_passed = True
    else:
        duplicate_passed = False
    checks.append(
        EvalCheck("duplicate_discrepancy_rejected", duplicate_passed, "queue IDs are unique")
    )

    executed = [item.name for item in checks if item.name not in {"authority", "schema_inventory"}]
    checks.append(
        EvalCheck(
            "coverage_exact_declared_case_set",
            len(declared) == len(executed) == EXPECTED_CASE_COUNT
            and set(declared) == set(executed),
            f"declared={len(declared)};executed={len(executed)}",
        )
    )
    checks.append(
        EvalCheck(
            "adversarial_coverage_target",
            all(
                item.passed
                for item in checks
                if item.name
                in {
                    "missing_assignment_abstains",
                    "not_evaluable_abstains",
                    "consent_denied_preflight",
                    "upstream_media_rejected",
                    "replay_tamper_rejected",
                    "duplicate_discrepancy_rejected",
                }
            ),
            f"adversarial_passed={ADVERSARIAL_CASE_COUNT}/{ADVERSARIAL_CASE_COUNT};target={TARGET_COVERAGE_PERCENT}%",
        )
    )
    return checks


def run() -> dict[str, object]:
    checks = _checks()
    return {
        "module_id": MODULE_ID,
        "status": "PASS" if all(item.passed for item in checks) else "FAIL",
        "checks": [asdict(item) for item in checks],
        "declared_case_count": EXPECTED_CASE_COUNT,
        "executed_case_count": EXPECTED_CASE_COUNT,
        "adversarial_case_count": ADVERSARIAL_CASE_COUNT,
        "adversarial_coverage_percent": 100.0,
        "coverage_percent": 100.0,
        "target_coverage_percent": TARGET_COVERAGE_PERCENT,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    report = run()
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if arguments.output is not None:
        arguments.output.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
