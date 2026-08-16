"""Focused runtime, service, plugin, and replay tests for M22-08."""

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m22_08 import (
    ApprovalDecision,
    ApprovalRecord,
    BenchmarkOutcome,
    GateDecision,
    GateFindingCode,
)
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.kernel.strict_json import StrictJsonError
from glio_proteogen.modules.c21_reference_material.m22_08_evidence_gate_release_adjudicator import (
    EvidenceGateSubmission,
    M2208AuthorizationError,
    M2208EvidenceGateEngine,
    M2208Plugin,
    M2208ReplayError,
    M2208Service,
    ValidatedM2208Request,
)
from tests.contract.test_m2208_contract import _artifact, _context, _request


def test_engine_adjudicates_supported_pass_and_replays() -> None:
    request = _request()
    engine = M2208EvidenceGateEngine()
    result = engine.adjudicate(request)
    assert result.release_record is not None
    assert result.release_record.decision is GateDecision.PASS
    assert result.support_decision.status is SupportStatus.SUPPORTED
    assert engine.replay(result).result_digest == result.result_digest


def test_engine_blocks_failed_benchmark_without_negative_inference() -> None:
    request = _request()
    benchmark = BenchmarkOutcome(
        benchmark_id="benchmark-release",
        name="release-evaluator",
        metric_name="pass_rate",
        observed_value=0.2,
        required_floor=0.95,
        passed=False,
        report_artifact=_artifact("benchmark-report"),
        evidence=(request.benchmarks[0].evidence[0],),
    )
    payload = request.model_dump(mode="python")
    payload["benchmarks"] = (benchmark,)
    failed = type(request).model_validate(payload)
    result = M2208EvidenceGateEngine().adjudicate(failed)
    assert result.release_record is not None
    assert result.release_record.decision is GateDecision.BLOCK
    assert result.findings[0].code is GateFindingCode.BENCHMARK_FAILED
    assert result.support_decision.status is SupportStatus.SUPPORTED


def test_engine_requires_review_for_deferred_approval() -> None:
    request = _request()
    original = request.approvals[0]
    approval = ApprovalRecord(
        approval_id=original.approval_id,
        approver_token=original.approver_token,
        role=original.role,
        decision=ApprovalDecision.DEFER,
        signature_digest=original.signature_digest,
        evidence=original.evidence,
    )
    payload = request.model_dump(mode="python")
    payload["approvals"] = (approval,)
    deferred = type(request).model_validate(payload)
    result = M2208EvidenceGateEngine().adjudicate(deferred)
    assert result.release_record is not None
    assert result.release_record.decision is GateDecision.REVIEW_REQUIRED
    assert result.findings[0].code is GateFindingCode.APPROVAL_MISSING


def test_engine_fails_closed_on_denied_control_before_validation() -> None:
    request = _request()
    denied = request.model_copy(update={"context": _context("request-m2208")})
    denied_context = denied.context.model_copy(
        update={
            "references": denied.context.references.model_copy(
                update={
                    "consent": denied.context.references.consent.model_copy(
                        update={"state": "revoked"}
                    )
                }
            )
        }
    )
    denied = denied.model_copy(update={"context": denied_context})
    with pytest.raises(M2208AuthorizationError):
        M2208EvidenceGateEngine().adjudicate(denied)


def test_service_and_plugin_enforce_validate_then_run() -> None:
    request = _request()
    service = M2208Service()
    typed = service.validate_request(request.model_dump(mode="python"))
    assert typed.request_id == request.request_id
    result = service.adjudicate(request.model_dump_json())
    plugin = M2208Plugin(service)
    token = plugin.validate(EvidenceGateSubmission(request.model_dump_json()))
    assert isinstance(token, ValidatedM2208Request)
    assert plugin.run(token).result_digest == result.result_digest
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]


def test_replay_rejects_tampered_digest_and_identifier() -> None:
    result = M2208EvidenceGateEngine().adjudicate(_request())
    tampered_digest = result.model_copy(update={"result_digest": "sha256:" + "f" * 64})
    with pytest.raises(M2208ReplayError, match="payload digest"):
        M2208EvidenceGateEngine().replay(tampered_digest)
    tampered_id = result.model_copy(update={"result_id": "adjudication.m2208." + "0" * 64})
    with pytest.raises(M2208ReplayError, match="identifier"):
        M2208EvidenceGateEngine().replay(tampered_id)


def test_service_rejects_malformed_json_and_oversized_payload() -> None:
    service = M2208Service()
    with pytest.raises((ValidationError, ValueError)):
        service.validate_request(b"{not-json")
    with pytest.raises(StrictJsonError, match="exceeds the byte limit"):
        service.validate_request(b"x" * (8 * 1024 * 1024 + 1))
