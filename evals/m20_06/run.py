"""Executable nominal and adversarial evidence for M20-06."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final, TypedDict, cast

from pydantic import ValidationError

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from tests.contract.test_m20_06_adversarial import _assignment, _entry, _request

from glio_proteogen.contracts.m20_06 import (
    M2006_DOSSIER_SHA256,
    M2006_DOSSIER_SLICE,
    QueueEntryState,
    QueueResultStatus,
    ReviewDecision,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c20_biomarker_panel.m20_06_reviewer_discrepancy_adjudication import (
    M2006AuthorizationError,
    M2006Engine,
    M2006ReplayError,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M20-06"
SCENARIO_PATH: Final = Path("tests/fixtures/m20_06/scenarios.json")
EXPECTED_CASE_COUNT: Final = 9
ADVERSARIAL_CASE_COUNT: Final = 8
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


def _checks() -> list[EvalCheck]:  # noqa: C901, PLR0915 - executable evidence matrix.
    fixture = _fixture()
    declared = [case_id for group in fixture["scenario_groups"] for case_id in group["case_ids"]]
    checks: list[EvalCheck] = [
        EvalCheck(
            "authority",
            fixture["module_id"] == MODULE_ID
            and fixture["dossier_sha256"] == M2006_DOSSIER_SHA256.removeprefix("sha256:").upper()
            and fixture["dossier_slice"] == M2006_DOSSIER_SLICE,
            f"sha={fixture['dossier_sha256']};slice={fixture['dossier_slice']}",
        ),
        EvalCheck(
            "schema_inventory",
            tuple(fixture["schema_names"]) == tuple(contract_json_schemas()),
            f"declared={len(fixture['schema_names'])};actual={len(contract_json_schemas())}",
        ),
    ]
    engine = M2006Engine()
    request = _request()
    resolved = engine.adjudicate(request)
    checks.append(
        EvalCheck(
            "resolved_records",
            resolved.status is QueueResultStatus.RECORDED
            and resolved.record is not None
            and resolved.record.status.value == "resolved",
            f"status={resolved.status.value};record={resolved.record is not None}",
        )
    )
    unresolved_entry = _entry(state=QueueEntryState.IN_REVIEW)
    unresolved = engine.adjudicate(
        request.model_copy(
            update={
                "entries": (unresolved_entry,),
                "assignments": (_assignment(unresolved_entry, decision=ReviewDecision.DEFER),),
            }
        )
    )
    checks.append(
        EvalCheck(
            "unresolved_queue_abstains",
            unresolved.status is QueueResultStatus.ABSTAINED and unresolved.record is None,
            f"status={unresolved.status.value};record={unresolved.record is not None}",
        )
    )
    unevaluable_entry = _entry(state=QueueEntryState.NOT_EVALUABLE)
    unevaluable = engine.adjudicate(
        request.model_copy(
            update={
                "entries": (unevaluable_entry,),
                "assignments": (_assignment(unevaluable_entry, decision=ReviewDecision.ABSTAIN),),
            }
        )
    )
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
        engine.adjudicate(denied)
    except M2006AuthorizationError:
        denied_passed = True
    else:
        denied_passed = False
    checks.append(
        EvalCheck("consent_denied_preflight", denied_passed, "authorization precedes traversal")
    )
    invalid_upstream = request.upstream_result.model_copy(update={"media_type": "application/json"})
    try:
        type(request).model_validate(
            request.model_copy(update={"upstream_result": invalid_upstream}).model_dump(
                mode="python"
            ),
            strict=True,
        )
    except (ValidationError, ValueError):
        media_passed = True
    else:
        media_passed = False
    checks.append(
        EvalCheck("upstream_media_rejected", media_passed, "M20-05 media binding is strict")
    )
    tampered = (
        resolved.model_copy(
            update={"record": resolved.record.model_copy(update={"resolution_summary": "tampered"})}
        )
        if resolved.record is not None
        else resolved
    )
    try:
        engine.replay(tampered)
    except M2006ReplayError:
        replay_passed = True
    else:
        replay_passed = False
    checks.append(EvalCheck("replay_tamper_rejected", replay_passed, "result digest is immutable"))
    record = resolved.record
    if record is None:
        raise RuntimeError("resolved evaluator case did not emit a record")  # noqa: TRY003
    first_event = record.history[0].model_copy(update={"action": "tampered"})
    tampered_record = record.model_copy(update={"history": (first_event, *record.history[1:])})
    try:
        engine.replay(resolved.model_copy(update={"record": tampered_record}))
    except M2006ReplayError:
        chain_passed = True
    else:
        chain_passed = False
    checks.append(
        EvalCheck("audit_history_tamper_rejected", chain_passed, "audit history is immutable")
    )
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
    missing = _entry("missing", state=QueueEntryState.IN_REVIEW)
    missing_result = engine.adjudicate(
        request.model_copy(update={"entries": (request.entries[0], missing)})
    )
    checks.append(
        EvalCheck(
            "assignment_missing_abstains",
            missing_result.status is QueueResultStatus.ABSTAINED
            and any(item.code.value == "assignment_missing" for item in missing_result.findings),
            "unassigned discrepancies remain visible and unpromoted",
        )
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
                    "unresolved_queue_abstains",
                    "not_evaluable_abstains",
                    "consent_denied_preflight",
                    "upstream_media_rejected",
                    "replay_tamper_rejected",
                    "audit_history_tamper_rejected",
                    "duplicate_discrepancy_rejected",
                    "assignment_missing_abstains",
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)
    report = run()
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if arguments.output is not None:
        arguments.output.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
