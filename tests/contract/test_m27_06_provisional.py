"""Focused schema and security-control smoke for provisional M27-06."""

from typing import cast

import pytest
from evals.m27_06.fixture import build_request
from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m27_06 import (
    M2706_M2705_INPUT_MEDIA_TYPE,
    M2706_OUTPUT_MEDIA_TYPE,
    M2706_PROVISIONAL_ABI,
    AccessDecisionState,
    SecurityAssessmentStatus,
    SecurityControlKind,
    SecurityPostureStatus,
    contract_json_schemas,
)

_SCHEMA_COUNT = 8
_CONTROL_COUNT = 8


def test_provisional_schemas_require_security_and_safe_failure_controls() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert tuple(schemas) == (
        "request",
        "output",
        "access-decision",
        "audit-event",
        "posture",
        "control",
        "finding",
        "safe-failure",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert metadata["provisionalAbi"] is True
        assert metadata["leastPrivilegeRequired"] is True
        assert metadata["consentEnforcementRequired"] is True
        assert metadata["deIdentificationRequired"] is True
        assert metadata["auditRequired"] is True
        assert metadata["threatDetectionRequired"] is True
        assert metadata["safeFailureRequired"] is True
        assert metadata["unsupportedToNegative"] is False
        assert metadata["parentTarget"] == "complex activity"
        assert metadata["upstreamInputMediaType"] == M2706_M2705_INPUT_MEDIA_TYPE
    output_metadata = cast("dict[str, object]", schemas["output"]["x-glio-contract"])
    assert output_metadata["outputMediaType"] == M2706_OUTPUT_MEDIA_TYPE
    assert M2706_PROVISIONAL_ABI is True


def test_security_states_and_all_required_controls_are_explicit() -> None:
    assert len(tuple(SecurityControlKind)) == _CONTROL_COUNT
    assert AccessDecisionState.ABSTAIN_UNSUPPORTED.value == "abstain_unsupported"
    assert SecurityAssessmentStatus.ABSTAINED.value == "abstained"
    assert SecurityPostureStatus.NOT_EVALUABLE.value == "not_evaluable"


def test_contract_rejects_partial_controls_and_context_identity_drift() -> None:
    request = build_request()
    payload = request.model_dump(mode="json")
    payload["requested_controls"] = ["least_privilege"]
    with pytest.raises(ValueError, match=r".+"):
        type(request).model_validate(payload, strict=True)
    payload = request.model_dump(mode="json")
    payload["context"]["request_id"] = "m2706.request.other"
    with pytest.raises(ValueError, match=r".+"):
        type(request).model_validate(payload, strict=True)
