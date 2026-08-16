"""Focused schema and ownership smoke for provisional M16-07."""

from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m16_07 import (
    M1607_OUTPUT_MEDIA_TYPE,
    M1607_PROVISIONAL_ABI,
    CompatibilityReport,
    CompatibilityStatus,
    contract_json_schemas,
)

_SCHEMA_COUNT = 8


def test_provisional_schemas_require_signed_ownership_semantics() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert tuple(schemas) == (
        "request",
        "output",
        "field",
        "contract",
        "compatibility-report",
        "configuration",
        "policy",
        "finding",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = schema["x-glio-contract"]
        assert metadata["provisionalAbi"] is True
        assert metadata["versionedImmutableRequired"] is True
        assert metadata["ownershipSemanticsRequired"] is True
        assert metadata["unsupportedToNegative"] is False
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1607_OUTPUT_MEDIA_TYPE
    assert M1607_PROVISIONAL_ABI is True


def test_compatibility_report_is_auditable() -> None:
    report = CompatibilityReport(
        report_id="report-1",
        version="1.0.0",
        status=CompatibilityStatus.INCOMPATIBLE,
        consumer_id="consumer-1",
        reasons=("Ownership is not compatible.",),
    )
    assert report.auditable is True


def test_compatibility_is_not_silently_negative() -> None:
    assert CompatibilityStatus.REVIEW_REQUIRED.value == "review_required"
