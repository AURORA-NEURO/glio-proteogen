"""Deep boundary, replay, malformed-input and safe-abstention adversaries for M26-08."""

from __future__ import annotations

from typing import cast

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m26_08 import (
    ProteinSubtypeRetirementResult,
    RetirementCriterion,
    RetireProteinSubtypeServiceRequest,
    contract_json_schemas,
)
from glio_proteogen.kernel.strict_json import StrictJsonError
from glio_proteogen.modules.c20_biomarker_panel.m26_08_retirement_archival_knowledge_transfer import (  # noqa: E501
    M2608Plugin,
    M2608ReplayError,
    M2608RetirementService,
    RetirementSubmission,
)
from tests.runtime.test_m2608_runtime import _request


def test_request_rejects_unknown_fields() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="extra_forbidden"):
        RetireProteinSubtypeServiceRequest.model_validate(
            request.model_dump(mode="python") | {"unapproved_field": True}
        )


def test_result_rejects_unknown_fields() -> None:
    result = M2608RetirementService().retire(_request())
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ProteinSubtypeRetirementResult.model_validate(
            result.model_dump(mode="python") | {"unapproved_field": True}
        )


def test_plugin_rejects_duplicate_json_keys() -> None:
    with pytest.raises(StrictJsonError):
        M2608Plugin().validate(RetirementSubmission(b'{"request_id":"a","request_id":"b"}'))


def test_plugin_rejects_oversized_json() -> None:
    payload = b"{" + b'"x":' + b'"' + b"a" * (8 * 1024 * 1024) + b'"}'
    with pytest.raises(StrictJsonError):
        M2608Plugin().validate(RetirementSubmission(payload))


def test_replay_rejects_tampered_result_id() -> None:
    service = M2608RetirementService()
    result = service.retire(_request())
    tampered = result.model_copy(update={"result_id": "result.m2608.tampered"})
    with pytest.raises(M2608ReplayError):
        service.verify(tampered)


def test_replay_rejects_tampered_nested_package() -> None:
    service = M2608RetirementService()
    result = service.retire(_request())
    assert result.package is not None
    tampered_package = result.package.model_copy(update={"package_id": "package.tampered"})
    tampered = result.model_copy(update={"package": tampered_package})
    with pytest.raises(M2608ReplayError):
        service.verify(tampered)


def test_replay_rejects_tampered_request_content() -> None:
    service = M2608RetirementService()
    result = service.retire(_request())
    changed_criterion = result.request.criteria[0].model_copy(
        update={"statement": "changed after retirement"}
    )
    changed_request = result.request.model_copy(update={"criteria": (changed_criterion,)})
    tampered = result.model_copy(update={"request": changed_request})
    with pytest.raises(M2608ReplayError):
        service.verify(tampered)


def test_contract_does_not_relabel_unsupported_as_negative() -> None:
    metadata = [
        cast("dict[str, object]", schema["x-glio-contract"])
        for schema in contract_json_schemas().values()
    ]
    assert all(item["unsupportedToNegative"] is False for item in metadata)
    assert all(item["identityInference"] is False for item in metadata)
    assert all(item["consentInference"] is False for item in metadata)


def test_short_or_blank_criterion_text_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RetirementCriterion(
            criterion_id="criterion.bad",
            statement=" ",
            satisfied=True,
            evidence=(),
        )


def test_abstention_preserves_failed_material_as_findings() -> None:
    result = M2608RetirementService().retire(_request(criterion_satisfied=False))
    assert result.package is None
    assert result.findings
    assert result.findings[0].evidence
    assert result.abstention_reason is not None
