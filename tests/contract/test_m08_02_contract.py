"""Focused schema and lineage smoke for provisional M08-02 contracts."""

from typing import cast

from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m08_02 import (
    M0802_MAX_EVIDENCE,
    M0802_OUTPUT_MEDIA_TYPE,
    FeatureLineage,
    FeatureSpecification,
    LeakageCheck,
    LeakageCheckStatus,
    RepresentationTransformation,
    RepresentationTransformationKind,
    RepresentationValueKind,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference

_DIGEST = "sha256:" + ("a" * 64)


def _reference() -> ArtifactReference:
    return ArtifactReference(
        artifact_id="source." + "b" * 64,
        version="0.1.0",
        digest=_DIGEST,
        media_type="application/json",
    )


def test_feature_lineage_is_complete_and_ordered() -> None:
    transformation = RepresentationTransformation(
        sequence=1,
        kind=RepresentationTransformationKind.SCALING,
        name="locked-scale",
        parameters_digest=_DIGEST,
    )
    lineage = FeatureLineage(
        feature_id="feature.protein-abundance",
        source_artifacts=(_reference(),),
        source_fields=("abundance",),
        transformations=(transformation,),
    )
    specification = FeatureSpecification(
        feature_id=lineage.feature_id,
        version="0.1.0",
        value_kind=RepresentationValueKind.SCALAR,
        unit="normalized-abundance",
        dimension=1,
        lineage=lineage,
    )
    assert specification.lineage.leakage_safe is True
    assert specification.lineage.transformations[0].leakage_safe is True


def test_schema_exports_mark_lineage_and_leakage_requirements() -> None:
    schemas = contract_json_schemas()
    assert tuple(schemas) == (
        "request",
        "output",
        "feature-specification",
        "feature-lineage",
        "representation-feature",
        "transformation",
        "policy",
        "leakage-check",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert metadata["provisionalAbi"] is True
        assert metadata["featureLineageRequired"] is True
        assert metadata["leakageSafeTransformationsRequired"] is True
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M0802_OUTPUT_MEDIA_TYPE
    assert M0802_MAX_EVIDENCE > 0


def test_leakage_check_has_explicit_failure_states() -> None:
    check = LeakageCheck(
        check_id="leakage.split",
        status=LeakageCheckStatus.NOT_EVALUABLE,
        message="Held-out group metadata is not available in the provisional scaffold.",
    )
    assert check.status is LeakageCheckStatus.NOT_EVALUABLE
