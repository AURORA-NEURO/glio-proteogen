"""Deterministic M26-07 evaluator over a frozen scenario matrix."""

# ruff: noqa: T201, TRY003

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

from pydantic import ValidationError

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from tests.runtime.test_m2607_runtime import _request

from glio_proteogen.contracts.m26_07 import (
    M2607_MODULE_ID,
    ChangeStatus,
    ControlProteinSubtypeChangeRequest,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import SupportStatus, UpstreamDecisionState
from glio_proteogen.modules.c20_biomarker_panel.m26_07_change_control_rollback import (
    M2607AuthorizationError,
    M2607ChangeControlService,
    M2607Plugin,
    M2607ReplayError,
    RollbackSubmission,
)

DOSSIER_SHA256: Final = "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
DOSSIER_SLICE: Final = "GLIO-PROTEOGEN_240_Module_Dossier.md:9300-9340"
SCENARIO_PATH: Final = (
    Path(__file__).parents[2] / "tests" / "fixtures" / "m26_07" / "scenarios.json"
)
EXPECTED_CASE_IDS: Final = (
    "approved_complete",
    "failed_revalidation_abstention",
    "regression_contract_rejection",
    "authorization_gate",
    "plugin_parity",
    "replay_tamper",
    "deterministic_repeat",
    "schema_authority",
)
SCHEMA_COUNT: Final = 8


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
        raise ValueError("M26-07 fixture case IDs are not locked")
    request = _request()
    service = M2607ChangeControlService()
    checks: list[EvalCheck] = []

    approved = service.control(request)
    checks.append(
        EvalCheck(
            "approved_complete",
            approved.status is ChangeStatus.APPROVED
            and approved.change_package is not None
            and approved.rollback_point is not None,
            approved.result_digest,
        )
    )

    failed = (
        *request.revalidations,
        request.revalidations[0].model_copy(
            update={
                "revalidation_id": "revalidation.m2607.failed",
                "passed": False,
                "report_digest": "sha256:" + "e" * 64,
            }
        ),
    )
    abstained = service.control(request.model_copy(update={"revalidations": failed}))
    checks.append(
        EvalCheck(
            "failed_revalidation_abstention",
            abstained.status is ChangeStatus.ABSTAINED
            and abstained.change_package is None
            and abstained.support_decision.status is SupportStatus.REVIEW_REQUIRED,
            "failed non-required revalidation remains visible",
        )
    )

    regression = request.comparisons[0].model_copy(update={"no_regression": False})
    try:
        ControlProteinSubtypeChangeRequest.model_validate(
            request.model_dump(mode="python")
            | {"comparisons": (regression.model_dump(mode="python"),)}
        )
    except ValidationError:
        regression_rejected = True
    else:
        regression_rejected = False
    checks.append(
        EvalCheck("regression_contract_rejection", regression_rejected, "regression blocks")
    )

    rejected_support = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    rejected_references = request.context.references.model_copy(
        update={"support": rejected_support}
    )
    rejected_context = request.context.model_copy(update={"references": rejected_references})
    try:
        service.control(request.model_copy(update={"context": rejected_context}))
    except M2607AuthorizationError:
        authorization_gate = True
    else:
        authorization_gate = False
    checks.append(EvalCheck("authorization_gate", authorization_gate, "seven-control preflight"))

    plugin = M2607Plugin()
    plugin_result = plugin.run(plugin.validate(RollbackSubmission(request.model_dump_json())))
    checks.append(
        EvalCheck(
            "plugin_parity",
            plugin_result.model_dump(mode="json") == approved.model_dump(mode="json"),
            plugin_result.result_digest,
        )
    )

    tampered = approved.model_copy(update={"result_digest": "sha256:" + "f" * 64})
    try:
        service.verify(tampered)
    except M2607ReplayError:
        tamper_rejected = True
    else:
        tamper_rejected = False
    checks.append(EvalCheck("replay_tamper", tamper_rejected, "canonical digest mismatch rejected"))

    repeat = service.control(request)
    checks.append(
        EvalCheck(
            "deterministic_repeat",
            repeat.model_dump(mode="json") == approved.model_dump(mode="json"),
            approved.result_id,
        )
    )

    schemas = cast("dict[str, dict[str, Any]]", contract_json_schemas())
    schema_ok = len(schemas) == SCHEMA_COUNT and all(
        schema["x-glio-contract"]["moduleId"] == M2607_MODULE_ID
        and schema["x-glio-contract"]["provisionalAbi"] is True
        and schema["x-glio-contract"]["pendingOwnerConfirmation"] is True
        for schema in schemas.values()
    )
    checks.append(EvalCheck("schema_authority", schema_ok, str(len(schemas))))
    return {
        "module_id": M2607_MODULE_ID,
        "dossier_sha256": DOSSIER_SHA256,
        "dossier_slice": DOSSIER_SLICE,
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
