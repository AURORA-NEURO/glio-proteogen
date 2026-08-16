"""Schema and provisional boundary smoke tests for M24-04."""

from typing import Any, cast

from glio_proteogen.contracts.m24_04 import M2404_PROVISIONAL_ABI, contract_json_schemas

_SCHEMA_COUNT = 8


def test_provisional_schemas_require_external_transport_controls() -> None:
    schemas = cast("dict[str, dict[str, Any]]", contract_json_schemas())
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["externalTransportRequired"]
        and schema["x-glio-contract"]["independentSiteLabPlatformValidationRequired"]
        and schema["x-glio-contract"]["treatmentEraPopulationDiseaseClassSpecimenRequired"]
        and schema["x-glio-contract"]["calibrationFloorsRequired"]
        and schema["x-glio-contract"]["supportDomainNarrowingAllowed"]
        and schema["x-glio-contract"]["humanReviewRequired"]
        and schema["x-glio-contract"]["explicitAbstentionRequired"]
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["parentTarget"] == "biomarker panel"
        and schema["x-glio-contract"]["outputMediaType"].endswith("m24-04+json")
        for schema in schemas.values()
    )
    assert M2404_PROVISIONAL_ABI is True
