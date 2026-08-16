"""Focused contract/schema smoke for provisional M18-07."""

from typing import cast

from glio_proteogen.contracts.m18_07 import (
    M1807_OUTPUT_MEDIA_TYPE,
    M1807_PROVISIONAL_ABI,
    CompatibilityMode,
    ExportField,
    ExportFieldType,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference, EvidenceReference

_SCHEMA_COUNT = 8


def _metadata(schema: dict[str, object]) -> dict[str, object]:
    """Expose the contract metadata with a strict, test-local type."""

    return cast("dict[str, object]", schema["x-glio-contract"])


def test_provisional_schemas_preserve_typed_export_boundaries() -> None:
    schemas = contract_json_schemas()
    metadata = tuple(_metadata(schema) for schema in schemas.values())
    assert len(schemas) == _SCHEMA_COUNT
    assert all(str(schema["$schema"]).endswith("2020-12/schema") for schema in schemas.values())
    assert all(item["provisionalAbi"] for item in metadata)
    assert all(item["pendingOwnerConfirmation"] for item in metadata)
    assert all(
        item["documentedFieldsOnly"]
        and item["versionedCompatibilityRequired"]
        and item["immutableExportRequired"]
        and item["ownershipSemanticsRequired"]
        and item["consentAware"]
        and item["supportAware"]
        and item["signatureRequired"]
        and item["unsupportedToNegative"] is False
        for item in metadata
    )
    assert all(
        str(item["upstreamInputMediaType"]).endswith("m18-06+json")
        and item["parentTarget"] == "biomarker panel"
        for item in metadata
    )
    assert _metadata(schemas["output"])["outputMediaType"] == M1807_OUTPUT_MEDIA_TYPE
    assert M1807_PROVISIONAL_ABI is True


def test_field_schema_is_strict_and_compatibility_is_explicit() -> None:
    field = ExportField(
        field_id="field-1",
        field_name="spatial_proteotype",
        value_type=ExportFieldType.REFERENCE,
        field_version="0.1.0",
        owner="Platform engineering",
        documentation="Documented spatial proteotype export field.",
        value_digest="sha256:" + "a" * 64,
        evidence=(
            EvidenceReference(
                reference=ArtifactReference(
                    artifact_id="artifact-1",
                    version="0.1.0",
                    media_type="application/octet-stream",
                    digest="sha256:" + "b" * 64,
                ),
                role="evidence",
                claim="Field evidence.",
            ),
        ),
    )
    assert field.value_type is ExportFieldType.REFERENCE
    assert CompatibilityMode.VERSIONED.value == "versioned"
