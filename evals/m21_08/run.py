"""Deterministic evaluator over frozen M21-08 evidence-gate scenarios."""

# ruff: noqa: TRY003, T201

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import TypeAdapter
from tests.adversarial.test_m2108_adversarial import _artifact, _request

from glio_proteogen.contracts.m21_08 import (
    M2108_DOSSIER_SHA256,
    M2108_DOSSIER_SLICE,
    M2108_M2106_INPUT_MEDIA_TYPE,
    M2108_M2107_INPUT_MEDIA_TYPE,
    M2108_MODULE_ID,
    AdjudicateComplexActivityEvidenceGateRequest,
    ApprovalDecision,
    GateRunStatus,
    RiskSeverity,
)
from glio_proteogen.modules.c21_reference_material.m21_08_evidence_gate_release_adjudicator import (
    M2108AuthorizationError,
    M2108Engine,
)

MODULE_ID: Final = M2108_MODULE_ID
SCENARIO_PATH: Final = (
    Path(__file__).parents[2] / "tests" / "fixtures" / "m21_08" / "scenarios.json"
)
EXPECTED_CASE_IDS: Final = (
    "supported_adjudicated",
    "unsatisfied_requirement_abstention",
    "failed_benchmark_abstention",
    "critical_risk_abstention",
    "deferred_approval_abstention",
    "authorization_gate",
    "upstream_media_boundary",
    "source_media_boundary",
    "replay_tamper",
    "deterministic_repeat",
)


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def fixture_digest() -> str:
    return "sha256:" + hashlib.sha256(SCENARIO_PATH.read_bytes()).hexdigest()


def build_scenario_request() -> AdjudicateComplexActivityEvidenceGateRequest:
    return _request()


def run_evaluator() -> dict[str, object]:
    fixture = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    case_ids = tuple(item["case_id"] for item in fixture["cases"])
    if case_ids != EXPECTED_CASE_IDS:
        raise ValueError("M21-08 fixture case IDs are not locked")
    engine = M2108Engine()
    request = build_scenario_request()
    checks: list[EvalCheck] = []

    supported = engine.evaluate(request)
    checks.append(
        EvalCheck(
            "supported_adjudicated",
            supported.status is GateRunStatus.ADJUDICATED,
            supported.status.value,
        )
    )
    checks.append(
        EvalCheck(
            "unsatisfied_requirement_abstention",
            engine.evaluate(
                request.model_copy(
                    update={
                        "requirements": (
                            request.requirements[0].model_copy(update={"satisfied": False}),
                        )
                    }
                )
            ).status
            is GateRunStatus.ABSTAINED,
            "safe abstention",
        )
    )
    checks.append(
        EvalCheck(
            "failed_benchmark_abstention",
            engine.evaluate(
                request.model_copy(
                    update={
                        "benchmarks": (request.benchmarks[0].model_copy(update={"passed": False}),)
                    }
                )
            ).status
            is GateRunStatus.ABSTAINED,
            "safe abstention",
        )
    )
    checks.append(
        EvalCheck(
            "critical_risk_abstention",
            engine.evaluate(
                request.model_copy(
                    update={
                        "residual_risks": (
                            request.residual_risks[0].model_copy(
                                update={"severity": RiskSeverity.CRITICAL, "accepted": False}
                            ),
                        )
                    }
                )
            ).status
            is GateRunStatus.ABSTAINED,
            "safe abstention",
        )
    )
    checks.append(
        EvalCheck(
            "deferred_approval_abstention",
            engine.evaluate(
                request.model_copy(
                    update={
                        "approvals": (
                            request.approvals[0].model_copy(
                                update={"decision": ApprovalDecision.DEFER}
                            ),
                        )
                    }
                )
            ).status
            is GateRunStatus.ABSTAINED,
            "safe abstention",
        )
    )
    denied = request.context.references.approved_configuration.model_copy(
        update={"state": "rejected"}
    )
    denied_context = request.context.model_copy(
        update={
            "references": request.context.references.model_copy(
                update={"approved_configuration": denied}
            )
        }
    )
    try:
        engine.evaluate(request.model_copy(update={"context": denied_context}))
    except M2108AuthorizationError:
        authorization_ok = True
    else:
        authorization_ok = False
    checks.append(EvalCheck("authorization_gate", authorization_ok, "denied control rejected"))
    try:
        TypeAdapter(AdjudicateComplexActivityEvidenceGateRequest).validate_python(
            request.model_copy(
                update={"upstream_evidence": _artifact("wrong", "application/json")}
            ),
            strict=True,
        )
    except ValueError:
        media_ok = True
    else:
        media_ok = False
    checks.append(EvalCheck("upstream_media_boundary", media_ok, M2108_M2107_INPUT_MEDIA_TYPE))
    try:
        TypeAdapter(AdjudicateComplexActivityEvidenceGateRequest).validate_python(
            request.model_copy(update={"source_artifacts": (request.source_artifacts[0],)}),
            strict=True,
        )
    except ValueError:
        source_ok = True
    else:
        source_ok = False
    checks.append(EvalCheck("source_media_boundary", source_ok, M2108_M2106_INPUT_MEDIA_TYPE))
    tampered = supported.model_copy(update={"result_digest": "sha256:" + "f" * 64})
    try:
        engine.verify(tampered)
    except ValueError:
        tamper_ok = True
    else:
        tamper_ok = False
    checks.append(
        EvalCheck(
            "replay_tamper",
            tamper_ok and engine.verify(supported) == supported,
            "replay and tamper",
        )
    )
    repeat = engine.evaluate(request)
    checks.append(EvalCheck("deterministic_repeat", repeat == supported, supported.result_digest))
    return {
        "module_id": MODULE_ID,
        "dossier_sha256": M2108_DOSSIER_SHA256,
        "dossier_slice": M2108_DOSSIER_SLICE,
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
        "uncertainty_dimensions": 7,
    }


if __name__ == "__main__":
    print(json.dumps(run_evaluator(), sort_keys=True))
