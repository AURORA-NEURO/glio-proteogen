"""Deterministic M26-01 evaluator over a frozen registry matrix."""

# ruff: noqa: T201, TRY003

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

from pydantic import ValidationError
from tests.contract.test_m2601_deep import _request

from glio_proteogen.contracts.m26_01 import (
    M2601_DOSSIER_SHA256,
    M2601_DOSSIER_SLICE,
    RegisterProteinSubtypeRegistryRequest,
    RegistryEntryStatus,
    RegistryStatus,
    canonical_request_digest,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c20_biomarker_panel.m26_01_registry_configuration_service import (
    M2601AuthorizationError,
    M2601RegistryEngine,
    M2601Service,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M26-01"
SCENARIO_PATH: Final = (
    Path(__file__).parents[2] / "tests" / "fixtures" / "m26_01" / "scenarios.json"
)
EXPECTED_CASE_IDS: Final = (
    "registered_complete",
    "quarantined_abstention",
    "incompatible_configuration",
    "authorization_gate",
    "source_binding_boundary",
    "replay_tamper_determinism",
    "service_plugin_parity",
    "schema_authority",
)
_SCHEMA_COUNT = 8


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def fixture_digest() -> str:
    return "sha256:" + hashlib.sha256(SCENARIO_PATH.read_bytes()).hexdigest()


def run_evaluator() -> dict[str, object]:  # noqa: PLR0915 - frozen matrix remains explicit.
    fixture = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    case_ids = tuple(item["case_id"] for item in fixture["cases"])
    if case_ids != EXPECTED_CASE_IDS:
        raise ValueError("M26-01 fixture case IDs are not locked")
    engine = M2601RegistryEngine()
    checks: list[EvalCheck] = []
    request = _request()
    registered = engine.register(request)
    checks.append(
        EvalCheck(
            "registered_complete",
            registered.status is RegistryStatus.REGISTERED
            and registered.registry is not None
            and registered.active_configuration is not None,
            registered.result_digest,
        )
    )
    quarantined_entry = request.entries[0].model_copy(
        update={"status": RegistryEntryStatus.QUARANTINED}
    )
    quarantined = engine.register(
        request.model_copy(update={"entries": (quarantined_entry, *request.entries[1:])})
    )
    checks.append(
        EvalCheck(
            "quarantined_abstention",
            quarantined.status is RegistryStatus.ABSTAINED
            and quarantined.registry is None
            and quarantined.support_decision.status is SupportStatus.REVIEW_REQUIRED,
            quarantined.abstention_reason or "missing abstention",
        )
    )
    binding = request.active_configuration.bindings[0].model_copy(
        update={"compatibility_digest": sha256_digest("forged-compatibility")}
    )
    configuration = request.active_configuration.model_copy(
        update={"bindings": (binding, *request.active_configuration.bindings[1:])}
    )
    incompatible = engine.register(
        request.model_copy(update={"active_configuration": configuration})
    )
    checks.append(
        EvalCheck(
            "incompatible_configuration",
            incompatible.status is RegistryStatus.ABSTAINED,
            incompatible.findings[0].code.value,
        )
    )
    denied_support = request.context.references.support.model_copy(update={"state": "rejected"})
    denied_references = request.context.references.model_copy(update={"support": denied_support})
    denied_context = request.context.model_copy(update={"references": denied_references})
    try:
        engine.register(request.model_copy(update={"context": denied_context}))
    except M2601AuthorizationError:
        authorization = True
    else:
        authorization = False
    checks.append(EvalCheck("authorization_gate", authorization, "denied controls rejected"))
    payload = request.model_dump(mode="python")
    payload["source_artifacts"] = (*request.source_artifacts[:-1], request.source_artifacts[0])
    try:
        RegisterProteinSubtypeRegistryRequest.model_validate(payload)
    except ValidationError:
        source_boundary = True
    else:
        source_boundary = False
    checks.append(EvalCheck("source_binding_boundary", source_boundary, "source IDs are unique"))
    replay = engine.replay(registered)
    tampered = registered.model_copy(update={"result_digest": "sha256:" + "f" * 64})
    try:
        engine.replay(tampered)
    except ValueError:
        tamper_rejected = True
    else:
        tamper_rejected = False
    repeat = engine.register(request)
    checks.append(
        EvalCheck(
            "replay_tamper_determinism",
            replay == registered and tamper_rejected and repeat == registered,
            registered.result_digest,
        )
    )
    service = M2601Service()
    plugin_result = service.register(request.model_dump_json())
    checks.append(
        EvalCheck("service_plugin_parity", plugin_result == registered, plugin_result.result_id)
    )
    schemas = cast("dict[str, dict[str, Any]]", contract_json_schemas())
    schema_ok = len(schemas) == _SCHEMA_COUNT and all(
        schema["x-glio-contract"]["dossierSha256"] == M2601_DOSSIER_SHA256
        for schema in schemas.values()
    )
    checks.append(EvalCheck("schema_authority", schema_ok, str(len(schemas))))
    return {
        "module_id": MODULE_ID,
        "dossier_sha256": M2601_DOSSIER_SHA256,
        "dossier_slice": M2601_DOSSIER_SLICE,
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
