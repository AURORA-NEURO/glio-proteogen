"""Deterministic M26-08 evaluator over a frozen retirement scenario matrix."""

# ruff: noqa: T201, TRY003

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

from tests.runtime.test_m2608_runtime import _request

from glio_proteogen.contracts.m26_08 import (
    M2608_DOSSIER_SHA256,
    M2608_DOSSIER_SLICE,
    M2608_MODULE_ID,
    ArchiveStatus,
    MigrationStatus,
    RetirementRunStatus,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import SupportStatus, UpstreamDecisionState
from glio_proteogen.modules.c20_biomarker_panel.m26_08_retirement_archival_knowledge_transfer import (  # noqa: E501
    M2608AuthorizationError,
    M2608Plugin,
    M2608ReplayError,
    M2608RetirementService,
    RetirementSubmission,
)

SCENARIO_PATH: Final = (
    Path(__file__).parents[2] / "tests" / "fixtures" / "m26_08" / "scenarios.json"
)
EXPECTED_CASE_IDS: Final = (
    "executed_complete",
    "criterion_abstention",
    "migration_abstention",
    "archive_abstention",
    "active_dependency_abstention",
    "authorization_gate",
    "plugin_parity",
    "replay_tamper",
    "deterministic_repeat",
    "schema_authority",
)
SCHEMA_COUNT: Final = 10


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def fixture_digest() -> str:
    return "sha256:" + hashlib.sha256(SCENARIO_PATH.read_bytes()).hexdigest()


def run_evaluator() -> dict[str, object]:
    fixture = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    case_ids = tuple(item["case_id"] for item in fixture["cases"])
    if case_ids != EXPECTED_CASE_IDS:
        raise ValueError("M26-08 fixture case IDs are not locked")
    request = _request()
    service = M2608RetirementService()
    checks: list[EvalCheck] = []

    executed = service.retire(request)
    checks.append(
        EvalCheck(
            "executed_complete",
            executed.status is RetirementRunStatus.EXECUTED and executed.package is not None,
            executed.result_digest,
        )
    )

    criterion = service.retire(_request(criterion_satisfied=False))
    checks.append(
        EvalCheck(
            "criterion_abstention",
            criterion.status is RetirementRunStatus.ABSTAINED
            and criterion.package is None
            and criterion.support_decision.status is SupportStatus.REVIEW_REQUIRED,
            "unsatisfied criterion remains visible",
        )
    )

    migration = service.retire(_request(migration_status=MigrationStatus.BLOCKED))
    checks.append(
        EvalCheck(
            "migration_abstention",
            migration.status is RetirementRunStatus.ABSTAINED
            and any(
                item.code.value == "dependency_migration_incomplete" for item in migration.findings
            ),
            "blocked migration is not treated as completed",
        )
    )

    archive = service.retire(_request(archive_status=ArchiveStatus.PRESERVED))
    checks.append(
        EvalCheck(
            "archive_abstention",
            archive.status is RetirementRunStatus.ABSTAINED
            and archive.package is None
            and any(item.code.value == "archive_unverified" for item in archive.findings),
            "unverified archive remains review-required",
        )
    )

    active = service.retire(_request(active_dependencies=("dependency.m2608.active",)))
    checks.append(
        EvalCheck(
            "active_dependency_abstention",
            active.status is RetirementRunStatus.ABSTAINED
            and any(item.code.value == "active_dependency" for item in active.findings),
            "active dependency blocks retirement",
        )
    )

    rejected_support = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    rejected_references = request.context.references.model_copy(
        update={"support": rejected_support}
    )
    rejected_context = request.context.model_copy(update={"references": rejected_references})
    try:
        service.retire(request.model_copy(update={"context": rejected_context}))
    except M2608AuthorizationError:
        authorization_gate = True
    else:
        authorization_gate = False
    checks.append(EvalCheck("authorization_gate", authorization_gate, "seven-control preflight"))

    plugin = M2608Plugin()
    plugin_result = plugin.run(plugin.validate(RetirementSubmission(request.model_dump_json())))
    checks.append(
        EvalCheck(
            "plugin_parity",
            plugin_result.model_dump(mode="json") == executed.model_dump(mode="json"),
            plugin_result.result_digest,
        )
    )

    tampered = executed.model_copy(update={"result_digest": "sha256:" + "f" * 64})
    try:
        service.verify(tampered)
    except M2608ReplayError:
        tamper_rejected = True
    else:
        tamper_rejected = False
    checks.append(EvalCheck("replay_tamper", tamper_rejected, "canonical digest mismatch rejected"))

    repeat = service.retire(request)
    checks.append(
        EvalCheck(
            "deterministic_repeat",
            repeat.model_dump(mode="json") == executed.model_dump(mode="json"),
            executed.result_id,
        )
    )

    schemas = cast("dict[str, dict[str, Any]]", contract_json_schemas())
    schema_ok = len(schemas) == SCHEMA_COUNT and all(
        schema["x-glio-contract"]["moduleId"] == M2608_MODULE_ID
        and schema["x-glio-contract"]["provisionalAbi"] is True
        and schema["x-glio-contract"]["pendingOwnerConfirmation"] is True
        for schema in schemas.values()
    )
    checks.append(EvalCheck("schema_authority", schema_ok, str(len(schemas))))
    return {
        "module_id": M2608_MODULE_ID,
        "dossier_sha256": M2608_DOSSIER_SHA256,
        "dossier_slice": M2608_DOSSIER_SLICE,
        "fixture": str(SCENARIO_PATH),
        "fixture_digest": fixture_digest(),
        "case_ids": list(case_ids),
        "declared_cases": len(case_ids),
        "executed_cases": len(checks),
        "passed_cases": sum(item.passed for item in checks),
        "total_cases": len(checks),
        "checks": [
            {"name": item.name, "passed": item.passed, "detail": item.detail} for item in checks
        ],
        "passed": len(checks) == len(case_ids) and all(item.passed for item in checks),
        "schema_count": len(schemas),
        "uncertainty_dimensions": 7,
    }


if __name__ == "__main__":
    print(json.dumps(run_evaluator(), sort_keys=True))
