"""Focused contract/schema smoke for provisional M19-07."""

from typing import cast

from glio_proteogen.contracts.m19_07 import (
    M1907_OUTPUT_MEDIA_TYPE,
    M1907_PROHIBITED_CLAIM_TERMS,
    M1907_PROVISIONAL_ABI,
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
    for schema in schemas.values():
        assert cast("str", schema["$schema"]).endswith("2020-12/schema")
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert metadata["provisionalAbi"] is True
        assert metadata["pendingOwnerConfirmation"] is True
        for key in (
            "documentedFieldsOnly",
            "versionedCompatibilityRequired",
            "immutableExportRequired",
            "ownershipSemanticsRequired",
            "consentAware",
            "supportAware",
            "signatureRequired",
        ):
            assert metadata[key] is True
        assert metadata["unsupportedToNegative"] is False
        assert tuple(cast("list[str]", metadata["prohibitedClaimTerms"])) == (
            M1907_PROHIBITED_CLAIM_TERMS
        )
        assert cast("str", metadata["upstreamInputMediaType"]).endswith("m19-06+json")
        assert metadata["parentTarget"] == "proteotype"
    output_metadata = cast("dict[str, object]", schemas["output"]["x-glio-contract"])
    assert output_metadata["outputMediaType"] == M1907_OUTPUT_MEDIA_TYPE
    assert M1907_PROVISIONAL_ABI is True


def test_field_schema_is_strict_and_compatibility_is_explicit() -> None:
    field = ExportField(
        field_id="field-1",
        field_name="proteotype",
        value_type=ExportFieldType.REFERENCE,
        field_version="0.1.0",
        owner="Scientific engineering",
        documentation="Documented proteotype export field.",
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
