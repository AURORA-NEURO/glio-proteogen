"""Focused schema and security-control smoke for provisional M26-06."""

from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m26_06 import (
    M2606_M2605_INPUT_MEDIA_TYPE,
    M2606_OUTPUT_MEDIA_TYPE,
    M2606_PROVISIONAL_ABI,
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
        metadata = schema["x-glio-contract"]
        assert metadata["provisionalAbi"] is True
        assert metadata["leastPrivilegeRequired"] is True
        assert metadata["consentEnforcementRequired"] is True
        assert metadata["deIdentificationRequired"] is True
        assert metadata["auditRequired"] is True
        assert metadata["threatDetectionRequired"] is True
        assert metadata["safeFailureRequired"] is True
        assert metadata["unsupportedToNegative"] is False
        assert metadata["parentTarget"] == "protein subtype"
        assert metadata["upstreamInputMediaType"] == M2606_M2605_INPUT_MEDIA_TYPE
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M2606_OUTPUT_MEDIA_TYPE
    assert M2606_PROVISIONAL_ABI is True


def test_security_states_and_all_required_controls_are_explicit() -> None:
    assert len(tuple(SecurityControlKind)) == _CONTROL_COUNT
    assert AccessDecisionState.ABSTAIN_UNSUPPORTED.value == "abstain_unsupported"
    assert SecurityAssessmentStatus.ABSTAINED.value == "abstained"
    assert SecurityPostureStatus.NOT_EVALUABLE.value == "not_evaluable"
