"""Deterministic M26-04 gateway evaluator over a frozen scenario matrix."""

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

from tests.contract.test_m2604_contract import _request

from glio_proteogen.contracts.m26_04 import (
    M2604_DOSSIER_SHA256,
    M2604_DOSSIER_SLICE,
    AuthorizationDecision,
    CompatibilityStatus,
    GatewayStatus,
    JobStatus,
    PublishProteinSubtypeAccessSurfaceRequest,
    canonical_request_digest,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import SupportStatus as KernelSupportStatus
from glio_proteogen.modules.c20_biomarker_panel.m26_04_api_sdk_cli_gateway import (
    M2604AuthorizationError,
    M2604GatewayEngine,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M26-04"
SCENARIO_PATH: Final = (
    Path(__file__).parents[2] / "tests" / "fixtures" / "m26_04" / "scenarios.json"
)
EXPECTED_CASE_IDS: Final = (
    "published_complete",
    "denied_authorization_abstention",
    "queued_job_abstention",
    "migration_required_abstention",
    "authorization_gate",
    "source_closure_boundary",
    "replay_tamper_determinism",
    "schema_authority",
)
_SCHEMA_COUNT = 12


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def fixture_digest() -> str:
    return "sha256:" + hashlib.sha256(SCENARIO_PATH.read_bytes()).hexdigest()


def _abstained(request: PublishProteinSubtypeAccessSurfaceRequest, **updates: object) -> bool:
    result = M2604GatewayEngine().publish(request.model_copy(update=updates))
    return (
        result.status is GatewayStatus.ABSTAINED
        and result.access_surface is None
        and result.support_decision.status is KernelSupportStatus.REVIEW_REQUIRED
    )


def run_evaluator() -> dict[str, object]:
    fixture = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    case_ids = tuple(item["case_id"] for item in fixture["cases"])
    if case_ids != EXPECTED_CASE_IDS:
        raise ValueError("M26-04 fixture case IDs are not locked")
    request = _request()
    engine = M2604GatewayEngine()
    checks: list[EvalCheck] = []

    published = engine.publish(request)
    checks.append(
        EvalCheck(
            "published_complete",
            published.status is GatewayStatus.PUBLISHED and published.access_surface is not None,
            published.result_digest,
        )
    )

    denied = request.authorizations[0].model_copy(update={"decision": AuthorizationDecision.DENY})
    checks.append(
        EvalCheck(
            "denied_authorization_abstention",
            _abstained(request, authorizations=(denied,)),
            "denied operation is retained and not published",
        )
    )

    queued = request.jobs[0].model_copy(update={"status": JobStatus.QUEUED})
    checks.append(
        EvalCheck(
            "queued_job_abstention",
            _abstained(request, jobs=(queued,)),
            "queued asynchronous job requires completion",
        )
    )

    migration = request.compatibility_rules[0].model_copy(
        update={"status": CompatibilityStatus.MIGRATION_REQUIRED}
    )
    checks.append(
        EvalCheck(
            "migration_required_abstention",
            _abstained(request, compatibility_rules=(migration,)),
            "migration-required compatibility is not silently published",
        )
    )

    denied_support = request.context.references.support.model_copy(update={"state": "rejected"})
    denied_references = request.context.references.model_copy(update={"support": denied_support})
    denied_context = request.context.model_copy(update={"references": denied_references})
    try:
        engine.publish(request.model_copy(update={"context": denied_context}))
    except M2604AuthorizationError:
        authorization_gate = True
    else:
        authorization_gate = False
    checks.append(
        EvalCheck("authorization_gate", authorization_gate, "seven-control preflight rejected")
    )

    payload = request.model_dump(mode="python")
    payload["source_artifacts"] = (*request.source_artifacts[:-1], request.source_artifacts[0])
    try:
        PublishProteinSubtypeAccessSurfaceRequest.model_validate(payload)
    except ValidationError:
        source_boundary = True
    else:
        source_boundary = False
    checks.append(
        EvalCheck("source_closure_boundary", source_boundary, "duplicate source IDs rejected")
    )

    replay = engine.replay(published)
    tampered = published.model_copy(update={"result_digest": "sha256:" + "f" * 64})
    try:
        engine.replay(tampered)
    except ValueError:
        tamper_rejected = True
    else:
        tamper_rejected = False
    repeat = engine.publish(request)
    checks.append(
        EvalCheck(
            "replay_tamper_determinism",
            replay == published and tamper_rejected and repeat == published,
            published.result_digest,
        )
    )

    schemas = cast("dict[str, dict[str, Any]]", contract_json_schemas())
    schema_ok = len(schemas) == _SCHEMA_COUNT and all(
        schema["x-glio-contract"]["moduleId"] == MODULE_ID
        and schema["x-glio-contract"]["provisionalAbi"] is True
        and schema["x-glio-contract"]["pendingOwnerConfirmation"] is True
        for schema in schemas.values()
    )
    checks.append(EvalCheck("schema_authority", schema_ok, str(len(schemas))))
    return {
        "module_id": MODULE_ID,
        "dossier_sha256": M2604_DOSSIER_SHA256,
        "dossier_slice": M2604_DOSSIER_SLICE,
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
        "request_digest": canonical_request_digest(request),
        "uncertainty_dimensions": 7,
    }


if __name__ == "__main__":
    print(json.dumps(run_evaluator(), sort_keys=True))
