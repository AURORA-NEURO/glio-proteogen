"""Focused contract/schema smoke for provisional M20-07."""

from typing import Any, cast

from glio_proteogen.contracts.m20_07 import (
    M2007_DOSSIER_SHA256,
    M2007_DOSSIER_SLICE,
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
    schema_values = tuple(cast("dict[str, Any]", schema) for schema in schemas.values())
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["$schema"].endswith("2020-12/schema") for schema in schema_values)
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schema_values)
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schema_values)
    assert all(
        schema["x-glio-contract"]["documentedFieldsOnly"]
        and schema["x-glio-contract"]["versionedCompatibilityRequired"]
        and schema["x-glio-contract"]["immutableExportRequired"]
        and schema["x-glio-contract"]["ownershipSemanticsRequired"]
        and schema["x-glio-contract"]["consentAware"]
        and schema["x-glio-contract"]["supportAware"]
        and schema["x-glio-contract"]["signatureRequired"]
        and schema["x-glio-contract"]["unsupportedToNegative"] is False
        for schema in schema_values
    )
    assert all(
        schema["x-glio-contract"]["upstreamInputMediaType"].endswith("m20-06+json")
        and schema["x-glio-contract"]["parentTarget"] == "protein subtype"
        for schema in schema_values
    )
    output_metadata = cast("dict[str, Any]", schema_values[1]["x-glio-contract"])
    assert output_metadata["outputMediaType"] == M2007_OUTPUT_MEDIA_TYPE
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


def test_authority_and_provisional_upstream_binding_are_explicit() -> None:
    assert (
        M2007_DOSSIER_SHA256
        == "sha256:" + "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
    )
    assert M2007_DOSSIER_SLICE.endswith(":7140-7180")
