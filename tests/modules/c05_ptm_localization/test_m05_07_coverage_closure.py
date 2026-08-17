"""Adversarial closure for M05-07 canonical and result invariants."""

from __future__ import annotations

from typing import Any, cast

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m05_07 import (
    PtmLocalizationAbstentionCode,
    PtmLocalizationRemediationPath,
    PtmLocalizationSupportDimension,
    PtmLocalizationSupportDisposition,
    PtmLocalizationSupportReceipt,
    PtmLocalizationSupportRouteResult,
    receipt_digest,
    result_payload_digest,
)
from glio_proteogen.contracts.m05_07 import canonical as canonical_module
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.modules.c05_ptm_localization.m05_07_unsupported_abstention_router import (
    M0507Service,
    PtmLocalizationSupportAuthorizationError,
)
from glio_proteogen.modules.c05_ptm_localization.m05_07_unsupported_abstention_router import (
    engine as engine_module,
)
from tests.contract.test_m05_07_hardening import _request


def _receipt_payload() -> dict[str, Any]:
    return cast("dict[str, Any]", M0507Service().execute(_request()).receipt.model_dump())


def _result_payload() -> dict[str, Any]:
    result = M0507Service().execute(_request())
    payload = cast("dict[str, Any]", result.model_dump())
    payload["result_digest"] = result_payload_digest(payload)
    return payload


def test_canonical_mapping_projections_are_closed() -> None:
    request = _request().model_dump(mode="json")
    receipt = _receipt_payload()

    assert canonical_module.normalized_request(request) == request
    assert canonical_module.normalized_receipt(receipt) == receipt
    assert canonical_module.normalized_result_payload({"result_digest": "x", "value": 1}) == {
        "value": 1
    }


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "unsupported_dimensions",
            (PtmLocalizationSupportDimension.ASSAY, PtmLocalizationSupportDimension.ASSAY),
            "receipt unsupported dimensions must be unique",
        ),
        (
            "remediation",
            (
                PtmLocalizationRemediationPath.SUPPLY_REQUIRED_SUPPORT_EVIDENCE,
                PtmLocalizationRemediationPath.SUPPLY_REQUIRED_SUPPORT_EVIDENCE,
            ),
            "receipt remediation paths must be unique",
        ),
    ],
)
def test_receipt_rejects_duplicate_closure_values(
    field: str,
    value: tuple[object, ...],
    message: str,
) -> None:
    payload = _receipt_payload()
    payload[field] = value
    payload["receipt_digest"] = receipt_digest(payload)

    with pytest.raises(ValidationError, match=message):
        PtmLocalizationSupportReceipt.model_validate(payload)


def test_receipt_rejects_supported_abstention_material() -> None:
    payload = _receipt_payload()
    payload["remediation"] = (PtmLocalizationRemediationPath.CORRECT_SUPPORT_DECLARATION,)
    payload["receipt_digest"] = receipt_digest(payload)

    with pytest.raises(ValidationError, match="supported receipt cannot carry"):
        PtmLocalizationSupportReceipt.model_validate(payload)


def test_receipt_rejects_incomplete_abstention() -> None:
    payload = _receipt_payload()
    payload["disposition"] = PtmLocalizationSupportDisposition.ABSTAINED
    payload["receipt_digest"] = receipt_digest(payload)

    with pytest.raises(ValidationError, match="abstained receipt requires"):
        PtmLocalizationSupportReceipt.model_validate(payload)


def test_result_rejects_receipt_request_binding_mismatch() -> None:
    payload = _result_payload()
    receipt = cast("dict[str, Any]", payload["receipt"])
    receipt["request_digest"] = "sha256:" + "0" * 64
    receipt["receipt_digest"] = receipt_digest(receipt)
    payload["result_digest"] = result_payload_digest(payload)

    with pytest.raises(ValidationError, match="receipt does not bind"):
        PtmLocalizationSupportRouteResult.model_validate(payload)


def test_result_rejects_receipt_disposition_and_code_mismatch() -> None:
    payload = _result_payload()
    receipt = cast("dict[str, Any]", payload["receipt"])
    receipt["disposition"] = PtmLocalizationSupportDisposition.ABSTAINED
    receipt["abstention_code"] = PtmLocalizationAbstentionCode.DIMENSION_INDETERMINATE
    receipt["remediation"] = (PtmLocalizationRemediationPath.CORRECT_SUPPORT_DECLARATION,)
    receipt["unsupported_dimensions"] = (PtmLocalizationSupportDimension.QUALITY,)
    receipt["receipt_digest"] = receipt_digest(receipt)
    payload["result_digest"] = result_payload_digest(payload)

    with pytest.raises(ValidationError, match="disposition does not match"):
        PtmLocalizationSupportRouteResult.model_validate(payload)


def test_result_rejects_abstention_code_and_remediation_mismatch() -> None:
    payload = _result_payload()
    payload["abstention_code"] = PtmLocalizationAbstentionCode.DIMENSION_INDETERMINATE
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValidationError, match="abstention code does not match"):
        PtmLocalizationSupportRouteResult.model_validate(payload)

    payload = _result_payload()
    payload["remediation"] = (PtmLocalizationRemediationPath.CORRECT_SUPPORT_DECLARATION,)
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValidationError, match="result remediation does not match"):
        PtmLocalizationSupportRouteResult.model_validate(payload)


def test_strict_validator_preserves_authorization_errors() -> None:
    payload = _request().model_dump(mode="json")
    payload["context"]["references"]["quality"]["state"] = UpstreamDecisionState.REJECTED.value

    with pytest.raises(PtmLocalizationSupportAuthorizationError):
        engine_module._validate_json_request(payload, _request().model_dump_json())
