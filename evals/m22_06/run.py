"""Deterministic evaluator over frozen M22-06 challenge scenarios."""

# ruff: noqa: C901, PLR0915, TRY003, T201

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import TypeAdapter

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from tests.adversarial.test_m2206_contract_adversarial import _artifact, _request

from glio_proteogen.contracts.m22_06 import (
    M2206_DOSSIER_SHA256,
    M2206_DOSSIER_SLICE,
    M2206_M2205_INPUT_MEDIA_TYPE,
    ChallengeDisposition,
    ChallengeProteinRnaDiscordanceRobustnessRequest,
    RobustnessStatus,
)
from glio_proteogen.modules.c21_reference_material.m22_06_robustness_shift_ood_challenge import (
    M2206AuthorizationError,
    M2206Engine,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M22-06"
SCENARIO_PATH: Final = (
    Path(__file__).parents[2] / "tests" / "fixtures" / "m22_06" / "scenarios.json"
)
EXPECTED_CASE_IDS: Final = (
    "supported_in_domain",
    "review_required_abstention",
    "unsupported_abstention",
    "authorization_gate",
    "upstream_media_boundary",
    "source_upstream_retention",
    "duplicate_scenario_rejection",
    "replay_tamper",
    "deterministic_repeat",
)


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def build_scenario_request() -> ChallengeProteinRnaDiscordanceRobustnessRequest:
    return _request()


def fixture_digest() -> str:
    return "sha256:" + hashlib.sha256(SCENARIO_PATH.read_bytes()).hexdigest()


def run_evaluator() -> dict[str, object]:
    fixture = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    case_ids = tuple(item["case_id"] for item in fixture["cases"])
    if case_ids != EXPECTED_CASE_IDS:
        raise ValueError("M22-06 fixture case IDs are not locked")
    engine = M2206Engine()
    request = build_scenario_request()
    checks: list[EvalCheck] = []
    supported = engine.evaluate(request)
    checks.append(
        EvalCheck(
            "supported_in_domain",
            supported.status is RobustnessStatus.EVALUATED
            and supported.robustness_surface is not None,
            supported.status.value,
        )
    )
    review_scenario = request.scenarios[0].model_copy(
        update={"expected_disposition": ChallengeDisposition.REVIEW_REQUIRED}
    )
    review = engine.evaluate(
        request.model_copy(update={"scenarios": (review_scenario, *request.scenarios[1:])})
    )
    checks.append(
        EvalCheck(
            "review_required_abstention",
            review.status is RobustnessStatus.ABSTAINED,
            review.status.value,
        )
    )
    unsupported_scenario = request.scenarios[0].model_copy(
        update={"expected_disposition": ChallengeDisposition.ABSTAIN_UNSUPPORTED}
    )
    unsupported = engine.evaluate(
        request.model_copy(update={"scenarios": (unsupported_scenario, *request.scenarios[1:])})
    )
    checks.append(
        EvalCheck(
            "unsupported_abstention",
            unsupported.status is RobustnessStatus.ABSTAINED,
            unsupported.status.value,
        )
    )
    denied = request.context.references.support.model_copy(update={"state": "rejected"})
    refs = request.context.references.model_copy(update={"support": denied})
    try:
        engine.evaluate(
            request.model_copy(
                update={"context": request.context.model_copy(update={"references": refs})}
            )
        )
    except M2206AuthorizationError:
        authorization_ok = True
    else:
        authorization_ok = False
    checks.append(EvalCheck("authorization_gate", authorization_ok, "denied control rejected"))
    try:
        TypeAdapter(ChallengeProteinRnaDiscordanceRobustnessRequest).validate_python(
            request.model_copy(update={"upstream_result": _artifact("wrong", "application/json")}),
            strict=True,
        )
    except ValueError:
        media_ok = True
    else:
        media_ok = False
    checks.append(EvalCheck("upstream_media_boundary", media_ok, M2206_M2205_INPUT_MEDIA_TYPE))
    source_only = request.model_dump(mode="python")
    source_only["source_artifacts"] = (_artifact("source-only"),)
    try:
        ChallengeProteinRnaDiscordanceRobustnessRequest.model_validate(source_only)
    except ValueError:
        retention_ok = True
    else:
        retention_ok = False
    checks.append(EvalCheck("source_upstream_retention", retention_ok, "M22-05 source retained"))
    duplicate = request.model_dump(mode="python")
    duplicate["scenarios"] = (request.scenarios[0], *request.scenarios)
    try:
        ChallengeProteinRnaDiscordanceRobustnessRequest.model_validate(duplicate)
    except ValueError:
        duplicate_ok = True
    else:
        duplicate_ok = False
    checks.append(EvalCheck("duplicate_scenario_rejection", duplicate_ok, "duplicate rejected"))
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
        "dossier_sha256": M2206_DOSSIER_SHA256,
        "dossier_slice": M2206_DOSSIER_SLICE,
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
