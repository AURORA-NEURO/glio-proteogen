"""Focused contract/schema smoke for provisional M20-07."""

from glio_proteogen.contracts.m20_07 import (
    M2007_OUTPUT_MEDIA_TYPE,
    M2007_PROVISIONAL_ABI,
    CompatibilityMode,
    ExportField,
    ExportFieldType,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference, EvidenceReference

_SCHEMA_COUNT = 8


def test_provisional_schemas_preserve_typed_export_boundaries() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["$schema"].endswith("2020-12/schema") for schema in schemas.values())
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["documentedFieldsOnly"]
        and schema["x-glio-contract"]["versionedCompatibilityRequired"]
        and schema["x-glio-contract"]["immutableExportRequired"]
        and schema["x-glio-contract"]["ownershipSemanticsRequired"]
        and schema["x-glio-contract"]["consentAware"]
        and schema["x-glio-contract"]["supportAware"]
        and schema["x-glio-contract"]["signatureRequired"]
        and schema["x-glio-contract"]["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["upstreamInputMediaType"].endswith("m20-06+json")
        and schema["x-glio-contract"]["parentTarget"] == "protein subtype"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M2007_OUTPUT_MEDIA_TYPE
    assert M2007_PROVISIONAL_ABI is True


def test_field_schema_is_strict_and_compatibility_is_explicit() -> None:
    field = ExportField(
        field_id="field-1",
        field_name="protein_subtype",
        value_type=ExportFieldType.ENUM,
        field_version="0.1.0",
        owner="Computational biology",
        documentation="Documented protein subtype export field.",
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
    assert field.value_type is ExportFieldType.ENUM
    assert CompatibilityMode.VERSIONED.value == "versioned"
