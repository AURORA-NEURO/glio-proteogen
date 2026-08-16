"""Focused contract/schema smoke for provisional M17-01."""

import pytest

from glio_proteogen.contracts.m17_01 import (
    M1701_DOSSIER_SHA256,
    M1701_DOSSIER_SLICE,
    M1701_OUTPUT_MEDIA_TYPE,
    M1701_PROVISIONAL_ABI,
    CompatibilityStatus,
    ResolverFindingCode,
    UpstreamSourceKind,
    contract_json_schemas,
)

_SCHEMA_COUNT = 9


def test_provisional_schemas_require_typed_resolution_controls() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["typedDiscoveryRequired"]
        and schema["x-glio-contract"]["versionCompatibilityRequired"]
        and schema["x-glio-contract"]["consentRequired"]
        and schema["x-glio-contract"]["provenancePreserved"]
        and schema["x-glio-contract"]["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["parentTarget"] == "variant peptide"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1701_OUTPUT_MEDIA_TYPE
    assert M1701_PROVISIONAL_ABI is True
    assert M1701_DOSSIER_SHA256.endswith(
        "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
    )
    assert M1701_DOSSIER_SLICE == "GLIO-PROTEOGEN_240_Module_Dossier.md:5796-5836"
    assert all(
        schema["x-glio-contract"]["dossierSlice"] == M1701_DOSSIER_SLICE
        for schema in schemas.values()
    )


def test_candidate_source_and_typed_unknown_path_are_explicit() -> None:
    assert UpstreamSourceKind.TRANSCRIPTOME.value == "transcriptome"
    assert CompatibilityStatus.UNKNOWN.value == "unknown"
    assert ResolverFindingCode.COMPATIBILITY_UNKNOWN.value == "compatibility_unknown"
    with pytest.raises(AssertionError):
        assert CompatibilityStatus.UNKNOWN is CompatibilityStatus.COMPATIBLE
