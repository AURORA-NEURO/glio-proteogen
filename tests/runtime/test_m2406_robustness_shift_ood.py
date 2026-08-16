"""Runtime, replay, provenance, and plugin tests for provisional M24-06."""

from __future__ import annotations

import pytest
from evals.m24_06.fixture import build_request, denied_request, review_request, unsupported_request
from pydantic import ValidationError

from glio_proteogen.contracts.m24_06 import RobustnessStatus
from glio_proteogen.kernel.models import SupportStatus, UpstreamDecisionState
from glio_proteogen.modules.c21_reference_material.m24_06_robustness_shift_ood_challenge import (
    M2406AuthorizationError,
    M2406Plugin,
    M2406ReplayError,
    M2406Service,
    RobustnessChallengeSubmission,
    ValidatedM2406Request,
    preflight_m2406_authorization,
)

_CHALLENGE_KIND_COUNT = 8
_CONTROL_COUNT = 7


def test_supported_challenge_is_deterministic_and_complete() -> None:
    service = M2406Service()
    first = service.challenge(build_request())
    second = service.challenge(build_request())
    assert first.status is RobustnessStatus.EVALUATED
    assert first.support_decision.status is SupportStatus.SUPPORTED
    assert first.robustness_surface is not None
    assert len(first.robustness_surface.observations) == _CHALLENGE_KIND_COUNT
    assert all(item.within_envelope for item in first.robustness_surface.observations)
    assert first.result_digest == second.result_digest
    assert first.result_id == second.result_id
    assert len(first.provenance.control_decisions) == _CONTROL_COUNT


def test_review_and_unsupported_challenges_abstain_with_safe_failure() -> None:
    service = M2406Service()
    for request in (review_request(), unsupported_request()):
        result = service.challenge(request)
        assert result.status is RobustnessStatus.ABSTAINED
        assert result.robustness_surface is None
        assert result.safe_failure_report is not None
        assert result.abstention_reason is not None
        assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
        assert result.human_review_required
        assert result.findings


def test_replay_rejects_request_identifier_and_payload_tampering() -> None:
    service = M2406Service()
    result = service.challenge(build_request())
    assert service.verify_replay(result).result_digest == result.result_digest
    with pytest.raises(M2406ReplayError, match="request digest"):
        service.verify_replay(result.model_copy(update={"request_digest": "sha256:" + "0" * 64}))
    with pytest.raises(M2406ReplayError, match="identifier"):
        service.verify_replay(result.model_copy(update={"result_id": "forged-result"}))
    with pytest.raises(M2406ReplayError, match="payload digest"):
        service.verify_replay(result.model_copy(update={"result_digest": "sha256:" + "0" * 64}))


def test_preflight_rejects_denied_and_malformed_controls() -> None:
    with pytest.raises(M2406AuthorizationError):
        M2406Service().challenge(denied_request())
    with pytest.raises(M2406AuthorizationError):
        preflight_m2406_authorization({"context": {}})
    denied = build_request().context.references.quality.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    references = build_request().context.references.model_copy(update={"quality": denied})
    changed = build_request().model_copy(
        update={"context": build_request().context.model_copy(update={"references": references})}
    )
    with pytest.raises(M2406AuthorizationError):
        M2406Service().validate_request(changed)


def test_service_requires_m2405_media_boundary() -> None:
    request = build_request()
    upstream = request.upstream_result.model_copy(update={"media_type": "application/json"})
    with pytest.raises(ValidationError, match="M24-05"):
        request.__class__.model_validate(
            request.model_dump(mode="python") | {"upstream_result": upstream}, strict=True
        )


def test_plugin_enforces_parse_once_and_capability_token() -> None:
    plugin = M2406Plugin(M2406Service())
    token = plugin.validate(
        RobustnessChallengeSubmission(request=build_request().model_dump_json())
    )
    assert isinstance(token, ValidatedM2406Request)
    result = plugin.run(token)
    assert plugin.replay(result).result_digest == result.result_digest
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M24-06"
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]
    with pytest.raises((ValidationError, M2406AuthorizationError)):
        plugin.validate(RobustnessChallengeSubmission(request=b'{"request_id":null}'))


def test_result_contract_rejects_forged_identity_and_unsafe_abstention() -> None:
    result = M2406Service().challenge(build_request())
    with pytest.raises(ValidationError, match="result identifier"):
        result.__class__.model_validate(
            result.model_dump(mode="python") | {"result_id": "forged"}, strict=True
        )
    abstained = M2406Service().challenge(unsupported_request())
    payload = abstained.model_dump(mode="python")
    payload["safe_failure_report"] = None
    with pytest.raises(ValidationError, match="safe failure"):
        abstained.__class__.model_validate(payload, strict=True)


__all__ = []
