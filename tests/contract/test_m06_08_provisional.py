"""Focused contract/runtime smoke for provisional M06-08."""

import pytest

from glio_proteogen.contracts.m06_08 import (
    M0608_MAX_EVIDENCE,
    M0608_OUTPUT_MEDIA_TYPE,
    contract_json_schemas,
)
from glio_proteogen.modules.c06_protein_abundance.m06_08_evidence_explanation_publisher import (
    M0608EvidencePublisherAuthorizationError,
    M0608Plugin,
    M0608Service,
    preflight_evidence_publisher_authorization,
)

_SCHEMA_COUNT = 8


def test_provisional_schemas_require_publication_evidence_fields() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["reconstructionEvidenceRequiredForPublication"]
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M0608_OUTPUT_MEDIA_TYPE
    assert M0608_MAX_EVIDENCE > 0


def test_plugin_descriptor_and_preflight_fail_closed() -> None:
    descriptor = M0608Plugin(M0608Service()).descriptor()
    assert descriptor.module_id == "GLIO-PROTEOGEN-M06-08"
    assert descriptor.version == "0.1.0-provisional"
    with pytest.raises(M0608EvidencePublisherAuthorizationError):
        preflight_evidence_publisher_authorization({"context": {"references": {}}})
