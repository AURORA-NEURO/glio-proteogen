"""Runtime, replay, and strict-boundary tests for M10-02."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

import pytest

from glio_proteogen.contracts.m10_02 import (
    ConstructProteinRnaRepresentationRequest,
    RepresentationConfiguration,
    RepresentationConstructionStatus,
    RepresentationFeatureValueKind,
    RepresentationInputFeature,
    RepresentationMethod,
    RepresentationMissingness,
    TransformationStep,
    canonical_request_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c10_pathway_proteotype.m10_02_representation_feature_constructor import (  # noqa: E501
    M1002Plugin,
    M1002Service,
    construct_protein_rna_representation,
    verify_result_replay,
)
from glio_proteogen.modules.c10_pathway_proteotype.m10_02_representation_feature_constructor.engine import (  # noqa: E501
    RepresentationAuthorizationError,
    _NonEvaluableTransformError,
    _plain,
    _RequestMappingError,
    _RequestTypeError,
    _UnsupportedOperationError,
    preflight_authorization,
    validate_json_request,
)


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{name}",
        version="1.0.0",
        digest=f"sha256:{sha256(name.encode()).hexdigest()}",
        media_type=media_type,
    )


def _upstream(name: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.{name}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=_artifact(f"ev{name}"),
    )


def _request(
    *, input_state: RepresentationMissingness = RepresentationMissingness.OBSERVED
) -> ConstructProteinRnaRepresentationRequest:
    formal_schema = _artifact("formal", "application/vnd.glio-proteogen.m10-01+json")
    evidence = _artifact("source")
    return ConstructProteinRnaRepresentationRequest(
        request_id="request.m1002",
        context=ExecutionContext(
            request_id="request.m1002",
            actor_id="actor.test",
            occurred_at=datetime(2026, 8, 15, tzinfo=UTC),
            references=ContextReferences(
                approved_configuration=_upstream("configuration"),
                identity_lineage=IdentityLineageReference(
                    decision_id="decision.identity",
                    state=IdentityLineageState.RESOLVED,
                    policy_version="1.0.0",
                    binding_digest=_artifact("identity").digest,
                    evidence=_artifact("identityev"),
                ),
                provenance=_upstream("provenance"),
                consent=ConsentReference(
                    decision_id="decision.consent",
                    state=ConsentState.GRANTED,
                    policy_version="1.0.0",
                    evidence=_artifact("consentev"),
                ),
                quality=_upstream("quality"),
                support=_upstream("support"),
                intended_use=_upstream("intended"),
            ),
        ),
        formal_state_schema=formal_schema,
        configuration=RepresentationConfiguration(
            configuration_id="config.m1002",
            version="1.0.0",
            method=RepresentationMethod.ELASTIC_NET_CONSEQUENCE,
            transformations=(
                TransformationStep(
                    transformation_id="transform.identity",
                    operation="identity",
                    input_feature_ids=("protein.alpha",),
                    output_feature_ids=("representation.alpha",),
                    fit_scope="none",
                ),
            ),
        ),
        input_features=(
            RepresentationInputFeature(
                feature_id="protein.alpha",
                value_kind=RepresentationFeatureValueKind.SCALAR,
                state=input_state,
                unit="log2_ratio",
                scalar_value=1.5 if input_state is RepresentationMissingness.OBSERVED else None,
            ),
        ),
        source_artifacts=(evidence,),
    )


def test_constructs_lineage_complete_representation_and_replays() -> None:
    request = _request()
    result = construct_protein_rna_representation(request)
    assert result.status is RepresentationConstructionStatus.CONSTRUCTED
    assert result.representation is not None
    assert result.representation.features[0].feature_id == "representation.alpha"
    assert result.representation.features[0].lineage.leakage_safe is True
    assert result.request_digest == canonical_request_digest(request)
    assert verify_result_replay(result) is True


def test_missing_input_abstains_without_negative_finding() -> None:
    result = construct_protein_rna_representation(
        _request(input_state=RepresentationMissingness.UNSUPPORTED)
    )
    assert result.status is RepresentationConstructionStatus.ABSTAINED
    assert result.representation is None
    assert result.support_decision.status.value == "review_required"
    assert result.human_review_required is True
    assert result.abstention_reason is not None


def test_controls_are_checked_before_execution() -> None:
    request = _request()
    references = request.context.references.model_copy(
        update={"support": _upstream("support").model_copy(update={"state": "rejected"})}
    )
    blocked = request.model_copy(
        update={"context": request.context.model_copy(update={"references": references})}
    )
    with pytest.raises(RepresentationAuthorizationError):
        M1002Service().execute(blocked)


def test_plugin_is_parse_once_and_rejects_unvalidated_execution() -> None:
    plugin = M1002Plugin(M1002Service())
    request = _request()
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M10-02"
    assert plugin.validate(request).request.request_id == request.request_id
    token = plugin.validate(request.model_dump_json())
    result = plugin.run(token)
    assert verify_result_replay(result)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(request)  # type: ignore[arg-type]


def test_json_validation_and_mapping_validation_preserve_strict_types() -> None:
    request = _request()
    assert validate_json_request({}, request.model_dump_json()).request_id == request.request_id
    assert M1002Service().validate_request(request.model_dump(mode="python")) == request


def test_transform_operations_cover_log1p_fitted_and_non_evaluable_paths() -> None:
    request = _request()
    log_configuration = request.configuration.model_copy(
        update={
            "transformations": (
                request.configuration.transformations[0].model_copy(update={"operation": "log1p"}),
            )
        }
    )
    log_request = request.model_copy(update={"configuration": log_configuration})
    assert construct_protein_rna_representation(log_request).status.value == "constructed"
    invalid_input = request.input_features[0].model_copy(update={"scalar_value": -1.0})
    invalid_request = request.model_copy(update={"input_features": (invalid_input,)})
    assert (
        construct_protein_rna_representation(
            invalid_request.model_copy(update={"configuration": log_configuration})
        ).status.value
        == "abstained"
    )
    fitted_configuration = request.configuration.model_copy(
        update={
            "transformations": (
                request.configuration.transformations[0].model_copy(
                    update={"operation": "standardize"}
                ),
            )
        }
    )
    assert (
        construct_protein_rna_representation(
            request.model_copy(update={"configuration": fitted_configuration})
        ).status.value
        == "constructed"
    )
    unsupported_configuration = request.configuration.model_copy(
        update={
            "transformations": (
                request.configuration.transformations[0].model_copy(
                    update={"operation": "future-method"}
                ),
            )
        }
    )
    assert (
        construct_protein_rna_representation(
            request.model_copy(update={"configuration": unsupported_configuration})
        ).status.value
        == "abstained"
    )


def test_categorical_and_vector_values_retain_declared_shapes() -> None:
    request = _request()
    categorical = request.input_features[0].model_copy(
        update={
            "value_kind": RepresentationFeatureValueKind.CATEGORICAL,
            "scalar_value": None,
            "category": "factor-a",
        }
    )
    vector = request.input_features[0].model_copy(
        update={
            "value_kind": RepresentationFeatureValueKind.VECTOR,
            "scalar_value": None,
            "vector": (0.1, 0.2),
        }
    )
    categorical_result = construct_protein_rna_representation(
        request.model_copy(update={"input_features": (categorical,)})
    )
    vector_result = construct_protein_rna_representation(
        request.model_copy(update={"input_features": (vector,)})
    )
    assert categorical_result.representation is not None
    assert categorical_result.representation.features[0].category == "factor-a"
    assert vector_result.representation is not None
    assert vector_result.representation.features[0].vector == (0.1, 0.2)


def test_preflight_rejects_hostile_and_incomplete_candidates() -> None:
    with pytest.raises(RepresentationAuthorizationError):
        preflight_authorization(object())
    with pytest.raises(RepresentationAuthorizationError):
        preflight_authorization({})


def test_defensive_error_types_and_plain_projection_are_exercised() -> None:
    assert str(_RequestTypeError())
    assert str(_RequestMappingError())
    assert str(_UnsupportedOperationError("future"))
    assert str(_NonEvaluableTransformError())
    assert _plain(_request())
    assert _plain([1, {"a": (2,)}]) == [1, {"a": (2,)}]
