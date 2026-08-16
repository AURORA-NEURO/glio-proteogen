"""Focused schema and rollback smoke for provisional M20-08."""

from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m20_08 import (
    M2008_M2007_INPUT_MEDIA_TYPE,
    M2008_OUTPUT_MEDIA_TYPE,
    M2008_PROVISIONAL_ABI,
    RollbackDecision,
    TranslationHealthStatus,
    contract_json_schemas,
)

_SCHEMA_COUNT = 8


def test_provisional_schemas_require_translation_health_and_rollback_controls() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert tuple(schemas) == (
        "request",
        "output",
        "report",
        "signal",
        "assessment",
        "rollback-plan",
        "configuration",
        "diagnostic",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = schema["x-glio-contract"]
        assert metadata["provisionalAbi"] is True
        assert metadata["usageTelemetryRequired"] is True
        assert metadata["supportDriftRequired"] is True
        assert metadata["suspensionAndRollbackExplicit"] is True
        assert metadata["unsupportedToNegative"] is False
        assert metadata["parentTarget"] == "protein subtype"
        assert metadata["upstreamInputMediaType"] == M2008_M2007_INPUT_MEDIA_TYPE
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M2008_OUTPUT_MEDIA_TYPE
    assert M2008_PROVISIONAL_ABI is True


def test_health_states_have_explicit_safe_decisions() -> None:
    assert TranslationHealthStatus.HEALTHY.value == "healthy"
    assert RollbackDecision.CONTINUE.value == "continue"
    assert TranslationHealthStatus.ABSTAINED.value == "abstained"
    assert RollbackDecision.ABSTAIN.value == "abstain"
