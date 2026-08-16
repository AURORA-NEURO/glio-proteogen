"""Runtime and replay gates for M18-07 downstream typed export."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m18_07 import ExportStatus
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.kernel.strict_json import StrictJsonError
from glio_proteogen.modules.c18_spatial_proteomics_projection.m18_07_downstream_typed_export import (  # noqa: E501
    M1807AuthorizationError,
    M1807Engine,
    M1807Plugin,
    M1807ReplayError,
    M1807Service,
    ValidatedM1807Request,
)

from .test_m18_07_deep import _request


def test_supported_export_contains_signed_contract_and_all_uncertainty() -> None:
    result = M1807Engine().export(_request())
    assert result.status is ExportStatus.EXPORTED
    assert result.contract is not None
    assert (
        result.contract.signature.signed_payload_digest
        != result.contract.signature.signature_digest
    )
    assert result.support_decision.status is SupportStatus.SUPPORTED
    assert result.provenance.module_id == "GLIO-PROTEOGEN-M18-07"
    assert result.uncertainty.support.state.value == "estimated"


def test_abstention_preserves_unsupported_status_and_no_contract() -> None:
    request = _request().model_copy(
        update={
            "support_decision": _request().support_decision.model_copy(
                update={"status": SupportStatus.UNSUPPORTED}
            )
        }
    )
    result = M1807Engine().export(request)
    assert result.status is ExportStatus.ABSTAINED
    assert result.contract is None
    assert result.support_decision.status is SupportStatus.UNSUPPORTED
    assert result.abstention_reason
    assert result.human_review_required


def test_preflight_rejects_denied_control_before_validation() -> None:
    request = _request()
    denied = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": request.context.references.model_copy(
                        update={
                            "quality": request.context.references.quality.model_copy(
                                update={"state": "rejected"}
                            )
                        }
                    )
                }
            )
        }
    )
    with pytest.raises(M1807AuthorizationError, match="quality"):
        M1807Engine().export(denied)


def test_replay_and_tamper_detection() -> None:
    engine = M1807Engine()
    result = engine.export(_request())
    assert engine.verify(result).result_digest == result.result_digest
    tampered = result.model_dump(mode="json")
    tampered["result_digest"] = "sha256:" + "a" * 64
    with pytest.raises((M1807ReplayError, ValidationError)):
        engine.verify(tampered)


def test_plugin_parse_once_seals_request_and_accepts_json() -> None:
    plugin = M1807Plugin(M1807Service())
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M18-07"
    token = plugin.validate(_request())
    assert plugin.run(token).status is ExportStatus.EXPORTED
    json_token = plugin.validate(canonical_json_bytes(_request()))
    assert plugin.run(json_token).status is ExportStatus.EXPORTED
    forged = ValidatedM1807Request(request=token.request, _seal=object())
    with pytest.raises(TypeError):
        plugin.run(forged)
    with pytest.raises(StrictJsonError, match="duplicate"):
        plugin.validate('{"request_id":"a","request_id":"b"}')
