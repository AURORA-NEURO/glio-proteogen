"""Adversarial closure for M27-04 boundaries and safe abstention."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m27_04 import (
    CompatibilityStatus,
    GatewayFindingCode,
    GatewayStatus,
    OperationStatus,
)
from glio_proteogen.kernel.strict_json import StrictJsonError
from glio_proteogen.modules.c20_biomarker_panel.m27_04_api_sdk_cli_gateway.engine import (
    M2704GatewayEngine,
    M2704ReplayError,
    preflight_m2704_authorization,
)
from glio_proteogen.modules.c20_biomarker_panel.m27_04_api_sdk_cli_gateway.plugin import (
    GatewaySubmission,
    M2704Plugin,
    M2704TokenError,
)
from glio_proteogen.modules.c20_biomarker_panel.m27_04_api_sdk_cli_gateway.service import (
    M2704Service,
)
from tests.runtime.test_m2704_runtime import _request


def test_mapping_and_json_inputs_preserve_one_canonical_result() -> None:
    request = _request()
    engine = M2704GatewayEngine()
    typed = engine.publish(request)
    mapping = engine.publish(request.model_dump(mode="json"))
    encoded = M2704Service().publish(request.model_dump_json())
    assert mapping == typed
    assert encoded == typed


def test_hostile_preflight_objects_fail_closed_without_traversal() -> None:
    with pytest.raises(ValueError, match="requires accepted configuration"):
        preflight_m2704_authorization({"context": {"references": object()}})


def test_disabled_operation_abstains_and_keeps_typed_finding() -> None:
    request = _request()
    operation = request.operations[0].model_copy(update={"status": OperationStatus.DISABLED})
    result = M2704GatewayEngine().publish(request.model_copy(update={"operations": (operation,)}))
    assert result.status is GatewayStatus.ABSTAINED
    assert any(item.code is GatewayFindingCode.OPERATION_UNAUTHORIZED for item in result.findings)


def test_unresolved_compatibility_abstains_without_negative_claim() -> None:
    request = _request()
    rule = request.compatibility_rules[0].model_copy(
        update={"status": CompatibilityStatus.MIGRATION_REQUIRED}
    )
    result = M2704GatewayEngine().publish(
        request.model_copy(update={"compatibility_rules": (rule,)})
    )
    assert result.status is GatewayStatus.ABSTAINED
    assert result.access_surface is None
    assert result.support_decision.status.value == "review_required"


def test_plugin_rejects_foreign_and_forged_capabilities() -> None:
    request = _request()
    first = M2704Plugin()
    second = M2704Plugin()
    token = first.validate(GatewaySubmission(request.model_dump_json()))
    with pytest.raises(M2704TokenError):
        second.run(token)
    with pytest.raises(M2704TokenError):
        first.run(object())  # type: ignore[arg-type]


def test_service_rejects_duplicate_keys_and_unknown_payload_fields() -> None:
    service = M2704Service()
    with pytest.raises((StrictJsonError, ValueError, ValidationError)):
        service.publish(b'{"request_id":"first","request_id":"second"}')
    payload = _request().model_dump(mode="json")
    payload["untrusted_claim"] = "not accepted"
    with pytest.raises((ValueError, ValidationError)):
        service.publish(payload)


def test_replay_rejects_forged_payload_and_plugin_metadata_is_closed() -> None:
    request = _request()
    result = M2704GatewayEngine().publish(request)
    forged = result.model_copy(update={"request_digest": "sha256:" + "0" * 64})
    with pytest.raises(M2704ReplayError):
        M2704GatewayEngine().replay(forged)
    descriptor = M2704Plugin.descriptor
    assert descriptor.provisional_abi is True
    assert descriptor.unsupported_to_negative is False
    assert descriptor.kinase_activity is False
    assert descriptor.all_omics_fusion is False
    assert descriptor.treatment_recommendation is False
    assert descriptor.identity_inference is False
    assert descriptor.consent_inference is False
