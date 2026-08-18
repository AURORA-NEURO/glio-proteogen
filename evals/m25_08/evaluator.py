"""Locked M25-08 evaluator matrix and hostile replay checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from evals.m25_08.fixture import build_request, denied_request
from glio_proteogen.contracts.m25_08 import ApprovalDecision, GateRunStatus, result_payload_digest
from glio_proteogen.modules.c21_reference_material import (
    m25_08_evidence_gate_release_adjudicator as m2508,
)

_ENGINE: Final = m2508.M2508Engine()
_REQUIREMENT_CATEGORIES = 6
_SOURCE_ARTIFACTS = 5
_CONTROL_DECISIONS = 7


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    name: str
    passed: bool
    status: str
    detail: str


def _nominal() -> ScenarioResult:
    result = _ENGINE.evaluate(build_request())
    return ScenarioResult(
        "nominal_adjudication",
        result.status is GateRunStatus.ADJUDICATED and result.release_record is not None,
        result.status.value,
        "all declared requirements, benchmark, risk, approval, and obligation controls pass",
    )


def _requirements_block() -> ScenarioResult:
    result = _ENGINE.evaluate(build_request(requirement_satisfied=False))
    return ScenarioResult(
        "unsatisfied_requirement_abstention",
        result.status is GateRunStatus.ABSTAINED and result.release_record is None,
        result.status.value,
        "unsatisfied traceability/control requirement is withheld for review",
    )


def _benchmark_block() -> ScenarioResult:
    result = _ENGINE.evaluate(build_request(benchmark_passed=False))
    return ScenarioResult(
        "benchmark_failure_abstention",
        result.status is GateRunStatus.ABSTAINED,
        result.status.value,
        "failed benchmark cannot be promoted as a release decision",
    )


def _risk_block() -> ScenarioResult:
    result = _ENGINE.evaluate(build_request(critical_risk_open=True))
    return ScenarioResult(
        "critical_risk_abstention",
        result.status is GateRunStatus.ABSTAINED,
        result.status.value,
        "open critical residual risk forces safe abstention",
    )


def _approval_review() -> ScenarioResult:
    result = _ENGINE.evaluate(build_request(approval_decision=ApprovalDecision.DEFER))
    return ScenarioResult(
        "approval_review_abstention",
        result.status is GateRunStatus.ABSTAINED
        and any(item.code.value == "approval_missing" for item in result.findings),
        result.status.value,
        "deferred approval is visible as a review finding",
    )


def _denied_control() -> ScenarioResult:
    try:
        _ENGINE.evaluate(denied_request())
    except m2508.M2508AuthorizationError:
        return ScenarioResult(
            "denied_control", passed=True, status="rejected", detail="preflight failed closed"
        )
    return ScenarioResult(
        "denied_control", passed=False, status="executed", detail="denied control executed"
    )


def _replay() -> ScenarioResult:
    result = _ENGINE.evaluate(build_request())
    replayed = _ENGINE.verify(result)
    return ScenarioResult(
        "canonical_replay",
        replayed.result_digest == result.result_digest,
        "verified",
        "request/result identity and payload digest replay exactly",
    )


def _determinism() -> ScenarioResult:
    first = _ENGINE.evaluate(build_request())
    second = _ENGINE.evaluate(build_request())
    return ScenarioResult(
        "deterministic_result_identity",
        first.result_id == second.result_id and first.result_digest == second.result_digest,
        "stable",
        "same canonical evidence yields same result identity and digest",
    )


def _dimension_closure() -> ScenarioResult:
    result = _ENGINE.evaluate(build_request())
    return ScenarioResult(
        "evidence_dimension_closure",
        len(result.request.requirements) == _REQUIREMENT_CATEGORIES
        and len(result.request.source_artifacts) == _SOURCE_ARTIFACTS
        and len(result.provenance.control_decisions) == _CONTROL_DECISIONS,
        result.status.value,
        "six gate categories, five evidence artifacts, and seven controls are retained",
    )


def run_scenarios() -> tuple[ScenarioResult, ...]:
    """Run the locked eight-scenario M25-08 matrix."""

    return (
        _nominal(),
        _requirements_block(),
        _benchmark_block(),
        _risk_block(),
        _approval_review(),
        _denied_control(),
        _replay(),
        _determinism(),
        _dimension_closure(),
    )


def _tamper() -> ScenarioResult:
    result = _ENGINE.evaluate(build_request())
    tampered = result.model_copy(
        update={
            "support_decision": result.support_decision.model_copy(
                update={"rationale": "Forged release approval."}
            )
        }
    )
    tampered = type(tampered).model_construct(
        **{**tampered.__dict__, "result_digest": result_payload_digest(tampered)}
    )
    try:
        _ENGINE.verify(tampered)
    except m2508.M2508ReplayError:
        try:
            _ENGINE.verify(result, replay=False)
        except m2508.M2508ReplayError:
            bypass_closed = True
        else:
            bypass_closed = False
        return ScenarioResult(
            "tamper_replay",
            passed=bypass_closed,
            status="rejected",
            detail="self-rehashed semantic mutation rejected by full replay",
        )
    return ScenarioResult(
        "tamper_replay", passed=False, status="accepted", detail="tamper was accepted"
    )


def run_adversarial() -> tuple[ScenarioResult, ...]:
    """Run hostile controls and replay checks used by release verification."""

    return (_denied_control(), _tamper(), _requirements_block(), _risk_block())


def evaluate() -> bool:
    return all(item.passed for item in (*run_scenarios(), *run_adversarial()))


__all__ = ["ScenarioResult", "evaluate", "run_adversarial", "run_scenarios"]
