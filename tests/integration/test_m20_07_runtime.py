"""Focused runtime and replay tests for M20-07."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m20_07 import ExportStatus
from glio_proteogen.kernel.models import ConsentState, SupportDecision, SupportStatus
from glio_proteogen.modules.c20_biomarker_panel.m20_07_downstream_typed_export import (
    M2007AuthorizationError,
    M2007Engine,
    M2007Plugin,
    M2007ReplayError,
    M2007Service,
)
from tests.contract.test_m20_07_hardening import _field, _request


def test_supported_export_is_deterministic_and_replayable() -> None:
    engine = M2007Engine()
    request = _request()
    first = engine.export(request)
    second = engine.export(request)
    assert first == second
    assert first.status is ExportStatus.EXPORTED
    assert first.contract is not None
    assert first.emits_parent is False
    assert first.human_review_required is False
    assert engine.verify(first) == first


def test_unsupported_export_abstains_without_contract() -> None:
    request = _request().model_copy(
        update={
            "support_decision": SupportDecision(
                status=SupportStatus.UNSUPPORTED,
                reason_code="upstream_unsupported",
                rationale="The caller-declared upstream result is outside support.",
            )
        }
    )
    result = M2007Engine().export(request)
    assert result.status is ExportStatus.ABSTAINED
    assert result.contract is None
    assert result.abstention_reason is not None
    assert result.human_review_required is True
    assert result.support_decision.status is SupportStatus.UNSUPPORTED


def test_prohibited_field_and_withheld_consent_fail_closed() -> None:
    request = _request().model_copy(
        update={"fields": (_field().model_copy(update={"documentation": "kinase treatment"}),)}
    )
    prohibited = M2007Engine().export(request)
    assert prohibited.status is ExportStatus.ABSTAINED
    assert any(item.code.value == "compatibility_mismatch" for item in prohibited.findings)

    withheld = request.context.references.consent.model_copy(
        update={"state": ConsentState.WITHHELD}
    )
    denied = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": request.context.references.model_copy(
                        update={"consent": withheld}
                    )
                }
            )
        }
    )
    with pytest.raises(M2007AuthorizationError):
        M2007Engine().export(denied)


def test_malformed_preflight_and_replay_tamper_are_safe() -> None:
    with pytest.raises(M2007AuthorizationError):
        M2007Engine().export({"context": {"references": None}})
    result = M2007Engine().export(_request())
    tampered = result.model_copy(update={"abstention_reason": "tampered"})
    with pytest.raises(M2007ReplayError):
        M2007Engine().verify(tampered, replay=False)


def test_service_and_plugin_share_canonical_execution() -> None:
    request = _request()
    service = M2007Service()
    service_result = service.execute(request)
    plugin = M2007Plugin(service)
    token = plugin.validate(json.dumps(request.model_dump(mode="json")).encode())
    assert plugin.run(token) == service_result
    assert plugin.verify(service_result) == service_result
    with pytest.raises(TypeError):
        plugin.run(request)  # type: ignore[arg-type]


def test_plugin_strict_json_rejects_duplicate_and_non_object_payloads() -> None:
    plugin = M2007Plugin()
    request = _request().model_dump(mode="json")
    payload = json.dumps(request, separators=(",", ":")).encode()
    assert plugin.run(plugin.validate(payload)).status is ExportStatus.EXPORTED
    with pytest.raises((TypeError, ValidationError, ValueError)):
        plugin.validate(b"[]")
    with pytest.raises((TypeError, ValidationError, ValueError)):
        plugin.validate(b'{"request_id":"x"}')
