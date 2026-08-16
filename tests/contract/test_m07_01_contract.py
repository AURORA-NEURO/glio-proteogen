"""Strict contract/schema smoke for the provisional M07-01 scaffold."""

from __future__ import annotations

from typing import cast

from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m07_01 import (
    M0701_OUTPUT_MEDIA_TYPE,
    CopyNumberFeatureDefinition,
    CopyNumberFeatureValue,
    CopyNumberFeatureValueKind,
    CopyNumberMissingness,
    canonical_request_digest,
    contract_json_schemas,
)

_EXPECTED_COPY_NUMBER = 2.0


def test_schema_inventory_is_explicitly_provisional() -> None:
    schemas = contract_json_schemas()
    assert tuple(schemas) == (
        "request",
        "output",
        "schema",
        "feature-definition",
        "feature-value",
        "invariant",
        "invariant-result",
        "migration",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert metadata["provisionalAbi"] is True
        assert metadata["abiStatus"] == "dossier-behavioral-brief-only"
        assert metadata["featureCatalogueFrozen"] is False
        assert metadata["migrationRulesFrozen"] is False
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M0701_OUTPUT_MEDIA_TYPE


def test_formal_feature_shape_and_canonical_smoke() -> None:
    definition = CopyNumberFeatureDefinition(
        feature_id="copy-number.total",
        version="1.0.0",
        value_kind=CopyNumberFeatureValueKind.SCALAR,
        unit="copy-number",
        allowed_missingness=(CopyNumberMissingness.OBSERVED, CopyNumberMissingness.MISSING),
        domain_lower=0.0,
    )
    value = CopyNumberFeatureValue(
        feature_id=definition.feature_id,
        state=CopyNumberMissingness.OBSERVED,
        unit=definition.unit,
        scalar_value=_EXPECTED_COPY_NUMBER,
    )
    assert value.scalar_value == _EXPECTED_COPY_NUMBER
    assert canonical_request_digest(
        {"definition": definition.model_dump(mode="json"), "value": value.model_dump(mode="json")}
    ).startswith("sha256:")
