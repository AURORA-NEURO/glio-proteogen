"""Focused schema and typed-rejection smoke for provisional M16-01."""

from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m16_01 import (
    M1601_OUTPUT_MEDIA_TYPE,
    M1601_PROVISIONAL_ABI,
    CompatibilityReport,
    CompatibilityStatus,
    UpstreamObjectKind,
    contract_json_schemas,
)

_SCHEMA_COUNT = 8


def test_provisional_schemas_require_typed_compatibility_controls() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert tuple(schemas) == (
        "request",
        "output",
        "candidate",
        "compatibility-report",
        "bundle",
        "configuration",
        "policy",
        "issue",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = schema["x-glio-contract"]
        assert metadata["provisionalAbi"] is True
        assert metadata["typedDiscoveryRequired"] is True
        assert metadata["typedRejectionsRequired"] is True
        assert metadata["unsupportedToNegative"] is False
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1601_OUTPUT_MEDIA_TYPE
    assert M1601_PROVISIONAL_ABI is True


def test_compatibility_report_is_auditable() -> None:
    report = CompatibilityReport(
        report_id="report-1",
        version="1.0.0",
        status=CompatibilityStatus.REJECTED,
        issues=(),
    )
    assert report.auditable is True
    assert report.all_rejections_typed is True


def test_upstream_kind_is_explicit() -> None:
    assert UpstreamObjectKind.CONSENT.value == "consent"
