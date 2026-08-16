"""Lightweight checks for the provisional M06-01 contract spine."""

from glio_proteogen.contracts.m06_01 import (
    M0601_MAX_FEATURES,
    M0601_OUTPUT_MEDIA_TYPE,
    FormalProteinStateSchema,
    FormalStateFeatureDefinition,
    FormalStateFeatureValue,
    FormalStateFeatureValueKind,
    FormalStateInvariant,
    FormalStateInvariantSeverity,
    FormalStateMissingness,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference


def _evidence() -> ArtifactReference:
    return ArtifactReference(
        artifact_id="schema." + "a" * 64,
        version="0.1.0",
        digest="sha256:" + "b" * 64,
        media_type="application/json",
    )


def test_formal_schema_accepts_feature_and_executable_invariant() -> None:
    feature = FormalStateFeatureDefinition(
        feature_id="protein.abundance",
        version="0.1.0",
        value_kind=FormalStateFeatureValueKind.SCALAR,
        unit="normalized-abundance",
        allowed_missingness=(FormalStateMissingness.OBSERVED, FormalStateMissingness.MISSING),
        domain_lower=0.0,
        evidence=(),
    )
    invariant = FormalStateInvariant(
        invariant_id="invariant.nonnegative",
        expression="protein.abundance >= 0",
        severity=FormalStateInvariantSeverity.ERROR,
        feature_ids=(feature.feature_id,),
    )
    schema = FormalProteinStateSchema(
        schema_id="schema.formal-state",
        version="0.1.0",
        features=(feature,),
        invariants=(invariant,),
    )
    assert schema.invariants[0].feature_ids == ("protein.abundance",)


def test_missing_feature_has_no_numeric_value() -> None:
    value = FormalStateFeatureValue(
        feature_id="protein.abundance",
        state=FormalStateMissingness.MISSING,
        unit="normalized-abundance",
    )
    assert value.scalar_value is None


def test_schema_exports_are_explicitly_provisional() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == M0601_MAX_FEATURES // 64
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M0601_OUTPUT_MEDIA_TYPE
