"""Runtime, replay, authorization, and interface tests for M13-03."""

from __future__ import annotations

import warnings
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m13_03 import (
    M1303_M1302_INPUT_MEDIA_TYPE,
    ConstructProteotypeMechanisticFeaturesRequest,
    MechanisticConstructionStatus,
    MechanisticDiagnosticStatus,
    MechanisticFeature,
    MechanisticFeatureConfiguration,
    MechanisticFeatureDiagnostic,
    MechanisticFeatureKind,
    MechanisticFeatureLineage,
    MechanisticFeatureObject,
    MechanisticRelation,
    MechanisticRelationKind,
    MechanisticValueKind,
    ProteotypeMechanisticFeatureResult,
    expected_uncertainty,
)
from glio_proteogen.contracts.m13_03.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
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
from glio_proteogen.modules.c11_protein_native_subtype import (
    m13_03_mechanistic_feature_constructor as m1303,
)

M1303Plugin = m1303.M1303Plugin
M1303Service = m1303.M1303Service
MechanisticFeatureAuthorizationError = m1303.MechanisticFeatureAuthorizationError
construct_proteotype_mechanistic_features = m1303.construct_proteotype_mechanistic_features
preflight_mechanistic_feature_authorization = m1303.preflight_mechanistic_feature_authorization
verify_mechanistic_feature_replay = m1303.verify_mechanistic_feature_replay


def artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1303": label}),
        media_type=media_type,
    )


def upstream(label: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.{label}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=artifact(f"evidence.{label}"),
    )


def request(
    *,
    source_label: str = "source.proteome",
    control_state: str = "accepted",
    negative_label: str = "negative.control",
) -> ConstructProteotypeMechanisticFeaturesRequest:
    state = UpstreamDecisionState(control_state)
    references = ContextReferences(
        approved_configuration=upstream("configuration"),
        identity_lineage=IdentityLineageReference(
            decision_id="decision.identity",
            state=IdentityLineageState.RESOLVED,
            policy_version="1.0.0",
            binding_digest=sha256_digest({"subject": "opaque"}),
            evidence=artifact("evidence.identity"),
        ),
        provenance=upstream("provenance"),
        consent=ConsentReference(
            decision_id="decision.consent",
            state=ConsentState.GRANTED,
            policy_version="1.0.0",
            evidence=artifact("evidence.consent"),
        ),
        quality=upstream("quality"),
        support=upstream("support"),
        intended_use=upstream("intended-use"),
    )
    if control_state != "accepted":
        references = references.model_copy(
            update={
                "quality": UpstreamDecisionReference(
                    decision_id="decision.quality",
                    state=state,
                    policy_version="1.0.0",
                    evidence=artifact("evidence.quality"),
                )
            }
        )
    context = ExecutionContext(
        request_id="context.request",
        actor_id="actor.test",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=references,
    )
    configuration = MechanisticFeatureConfiguration(
        configuration_id="configuration.m1303",
        version="1.0.0",
        model_family="curated-rule",
        transformation_ids=("transform.normalize",),
        pathway_reference=artifact("pathway.reference"),
        negative_control_artifacts=(artifact(negative_label),),
    )
    return ConstructProteotypeMechanisticFeaturesRequest(
        request_id="request.m1303",
        context=context,
        upstream_result=artifact("upstream", M1303_M1302_INPUT_MEDIA_TYPE),
        configuration=configuration,
        source_artifacts=(artifact(source_label),),
    )


def test_supported_request_constructs_interpretable_feature_object() -> None:
    result = construct_proteotype_mechanistic_features(request())

    assert result.status is MechanisticConstructionStatus.CONSTRUCTED
    assert result.feature_object is not None
    assert {feature.kind for feature in result.feature_object.features} >= {
        MechanisticFeatureKind.PATHWAY,
        MechanisticFeatureKind.TOPOLOGY,
    }
    assert all(item.status is MechanisticDiagnosticStatus.PASS for item in result.diagnostics)
    assert result.parent_target == "proteotype"
    assert result.emits_parent is False
    assert result.human_review_required


@pytest.mark.parametrize("label", ["unsupported.upstream", "missing.evidence", "ood.state"])
def test_unsupported_or_missing_evidence_abstains_without_feature_object(label: str) -> None:
    result = construct_proteotype_mechanistic_features(request(source_label=label))

    assert result.status is MechanisticConstructionStatus.ABSTAINED
    assert result.feature_object is None
    assert result.support_decision.status.value == "review_required"
    assert result.abstention_reason is not None


def test_negative_control_failure_abstains_with_fail_diagnostic() -> None:
    result = construct_proteotype_mechanistic_features(request(negative_label="control.fail"))

    assert result.status is MechanisticConstructionStatus.ABSTAINED
    assert result.diagnostics[0].status is MechanisticDiagnosticStatus.FAIL


def test_withheld_marker_is_not_converted_to_a_negative_finding() -> None:
    result = construct_proteotype_mechanistic_features(request(source_label="withheld.source"))

    assert result.status is MechanisticConstructionStatus.ABSTAINED
    assert result.abstention_reason == "source evidence is incomplete or not evaluable"


def test_denied_control_fails_closed_before_upstream_access() -> None:
    denied = request(control_state="rejected")

    with pytest.raises(MechanisticFeatureAuthorizationError):
        preflight_mechanistic_feature_authorization(denied)
    with pytest.raises(MechanisticFeatureAuthorizationError):
        construct_proteotype_mechanistic_features(denied)


def test_replay_verification_detects_tampering() -> None:
    result = construct_proteotype_mechanistic_features(request())
    tampered = result.model_copy(update={"findings": ()})
    assert verify_mechanistic_feature_replay(result).result_digest == result.result_digest
    # Replacing the sealed digest with the original is not enough after payload mutation.
    tampered = tampered.model_copy(update={"result_digest": result.result_digest})
    with pytest.raises(ValueError, match="replay verification failed"):
        verify_mechanistic_feature_replay(tampered)

    diagnostic = result.diagnostics[0].model_copy(update={"message": "forged diagnostic"})
    rehashed = result.model_copy(update={"diagnostics": (diagnostic, *result.diagnostics[1:])})
    rehashed = rehashed.model_copy(update={"result_digest": result_payload_digest(rehashed)})
    with pytest.raises(ValueError, match="replay verification failed"):
        verify_mechanistic_feature_replay(rehashed)


def test_plugin_accepts_strict_json_once() -> None:
    plugin = M1303Plugin(M1303Service())
    payload = request().model_dump_json()
    token = plugin.validate(payload)

    assert plugin.run(token).status is MechanisticConstructionStatus.CONSTRUCTED
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]


def test_plugin_rejects_duplicate_json_keys() -> None:
    plugin = M1303Plugin(M1303Service())
    with pytest.raises(ValueError, match="duplicate"):
        plugin.validate('{"request_id":"one","request_id":"two"}')


def test_feature_value_shape_is_strict() -> None:
    with pytest.raises(ValidationError, match="scalar feature requires"):
        MechanisticFeature(
            feature_id="feature.invalid",
            version="1.0.0",
            kind=MechanisticFeatureKind.STATE,
            value_kind=MechanisticValueKind.SCALAR,
            unit="score",
            lineage=MechanisticFeatureLineage(
                feature_id="feature.invalid",
                source_artifacts=(artifact("invalid"),),
                claim="Invalid fixture.",
            ),
        )


def test_expected_uncertainty_has_all_seven_dimensions() -> None:
    profile = expected_uncertainty()
    assert profile.measurement.probability == pytest.approx(0.8)
    assert profile.transport.state.value == "not_estimable"


def test_raw_dict_request_is_supported_only_when_controls_are_exact() -> None:
    candidate: dict[str, Any] = request().model_dump(mode="python")
    result = construct_proteotype_mechanistic_features(candidate)
    assert result.status is MechanisticConstructionStatus.CONSTRUCTED


def test_plugin_descriptor_and_typed_service_validation() -> None:
    plugin = M1303Plugin(M1303Service())
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M13-03"
    token = plugin.validate(request())
    assert token.request.request_id == "request.m1303"


def test_plugin_rejects_untyped_and_bytes_boundary_cases() -> None:
    plugin = M1303Plugin(M1303Service())
    with pytest.raises(MechanisticFeatureAuthorizationError):
        plugin.validate(object())
    with pytest.raises(ValueError, match="invalid JSON"):
        plugin.validate(b"not-json")
    with pytest.raises(TypeError, match="strict contract object"):
        plugin.validate("[]")
    bad_dict = request().model_dump(mode="python")
    bad_dict["operation"] = "wrong"
    with pytest.raises(TypeError, match="strict contract object"):
        plugin.validate(bad_dict)
    with pytest.raises(TypeError, match="strict contract object"):
        m1303.validate_json_request(request().model_dump(mode="python"), b"{}")


def test_preflight_hostile_and_untyped_candidates_fail_closed() -> None:
    for candidate in (object(), {"context": object()}, {"context": {"references": {}}}):
        with pytest.raises(MechanisticFeatureAuthorizationError):
            preflight_mechanistic_feature_authorization(candidate)
    with pytest.raises(ValueError, match="replay"):
        m1303.verify_mechanistic_feature_replay(object())
    result = construct_proteotype_mechanistic_features(request())
    with pytest.raises(ValueError, match="replay"):
        m1303.verify_mechanistic_feature_replay(
            result.model_copy(update={"request_digest": "sha256:" + "0" * 64})
        )


def test_replay_model_validation_rejects_constructed_tampering() -> None:
    result = construct_proteotype_mechanistic_features(request())
    payload = result.model_dump(mode="python")
    payload["feature_object"] = "not-an-object"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        shell = ProteotypeMechanisticFeatureResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(shell)
        sealed = ProteotypeMechanisticFeatureResult.model_construct(**payload)
        with pytest.raises(ValueError, match="replay"):
            m1303.verify_mechanistic_feature_replay(sealed)


def test_contract_feature_and_relation_invariants_are_adversarially_closed() -> None:
    feature = MechanisticFeature(
        feature_id="feature.state",
        version="1.0.0",
        kind=MechanisticFeatureKind.STATE,
        value_kind=MechanisticValueKind.INTERVAL,
        unit="normalized_state",
        lower_bound=0.5,
        upper_bound=0.7,
        lineage=MechanisticFeatureLineage(
            feature_id="feature.state",
            source_artifacts=(artifact("state"),),
            claim="State feature.",
            transformation_ids=("transform.normalize",),
        ),
    )
    with pytest.raises(ValidationError, match="ordered bounds"):
        MechanisticFeature.model_validate(
            feature.model_copy(update={"lower_bound": 0.9, "upper_bound": 0.7}).model_dump(
                mode="python"
            )
        )
    with pytest.raises(ValidationError, match="categorical feature"):
        MechanisticFeature(
            feature_id="feature.category",
            version="1.0.0",
            kind=MechanisticFeatureKind.STATE,
            value_kind=MechanisticValueKind.CATEGORICAL,
            unit="class",
            scalar_value=0.2,
            category="a",
            lineage=MechanisticFeatureLineage(
                feature_id="feature.category",
                source_artifacts=(artifact("category"),),
                claim="Category feature.",
            ),
        )
    with pytest.raises(ValidationError, match="self-loop"):
        MechanisticRelation(
            relation_id="relation.loop",
            source_feature_id="feature.state",
            target_feature_id="feature.state",
            kind=MechanisticRelationKind.REGULATES,
        )
    with pytest.raises(ValidationError, match="lineage id"):
        MechanisticFeature.model_validate(
            feature.model_copy(
                update={
                    "lineage": feature.lineage.model_copy(update={"feature_id": "feature.other"})
                }
            ).model_dump(mode="python")
        )


def test_contract_configuration_object_request_and_result_closures() -> None:
    good = request()
    with pytest.raises(ValidationError, match="transformation ids"):
        MechanisticFeatureConfiguration.model_validate(
            good.configuration.model_copy(update={"transformation_ids": ("x", "x")}).model_dump(
                mode="python"
            )
        )
    with pytest.raises(ValidationError, match="negative-control"):
        MechanisticFeatureConfiguration.model_validate(
            good.configuration.model_copy(
                update={"negative_control_artifacts": (artifact("a"), artifact("a"))}
            ).model_dump(mode="python")
        )
    with pytest.raises(ValidationError, match="provisional M13-02"):
        ConstructProteotypeMechanisticFeaturesRequest.model_validate(
            good.model_copy(update={"upstream_result": artifact("wrong")}).model_dump(mode="python")
        )
    with pytest.raises(ValidationError, match="alias"):
        request(negative_label="source.proteome")
    duplicate_sources = good.model_copy(
        update={"source_artifacts": (artifact("source.a"), artifact("source.a"))}
    )
    with pytest.raises(ValidationError, match="source artifact"):
        ConstructProteotypeMechanisticFeaturesRequest.model_validate(
            duplicate_sources.model_dump(mode="python")
        )

    result = construct_proteotype_mechanistic_features(good)
    assert result.feature_object is not None
    duplicate_features = result.feature_object.model_copy(
        update={"features": (result.feature_object.features[0], result.feature_object.features[0])}
    )
    with pytest.raises(ValidationError, match="feature ids"):
        MechanisticFeatureObject.model_validate(duplicate_features.model_dump(mode="python"))
    no_pathway = result.feature_object.model_copy(
        update={"features": result.feature_object.features[1:]}
    )
    with pytest.raises(ValidationError, match="pathway feature"):
        MechanisticFeatureObject.model_validate(no_pathway.model_dump(mode="python"))


def test_object_relations_lineage_diagnostics_and_result_closure() -> None:
    result = construct_proteotype_mechanistic_features(request())
    assert result.feature_object is not None
    obj = result.feature_object
    unknown_relation = obj.model_copy(
        update={
            "relations": (
                obj.relations[0].model_copy(update={"target_feature_id": "feature.unknown"}),
            )
        }
    )
    with pytest.raises(ValidationError, match="unknown feature"):
        MechanisticFeatureObject.model_validate(unknown_relation.model_dump(mode="python"))
    duplicate_relations = obj.model_copy(update={"relations": (obj.relations[0], obj.relations[0])})
    with pytest.raises(ValidationError, match="relation ids"):
        MechanisticFeatureObject.model_validate(duplicate_relations.model_dump(mode="python"))
    unknown_transformation = obj.features[0].model_copy(
        update={
            "lineage": obj.features[0].lineage.model_copy(
                update={"transformation_ids": ("transform.unknown",)}
            )
        }
    )
    with pytest.raises(ValidationError, match="unknown transformation"):
        MechanisticFeatureObject.model_validate(
            obj.model_copy(
                update={"features": (unknown_transformation, *obj.features[1:])}
            ).model_dump(mode="python")
        )
    with pytest.raises(ValidationError, match="at most 512"):
        MechanisticFeatureDiagnostic(
            diagnostic_id="diagnostic.long",
            status=MechanisticDiagnosticStatus.PASS,
            message="x" * 513,
        )

    with pytest.raises(ValueError, match="request digest"):
        ProteotypeMechanisticFeatureResult.model_validate(
            result.model_copy(update={"request_digest": "sha256:" + "0" * 64}).model_dump(
                mode="python"
            )
        )
    with pytest.raises(ValueError, match="evidence"):
        ProteotypeMechanisticFeatureResult.model_validate(
            result.model_copy(update={"evidence": ()}).model_dump(mode="python")
        )
    duplicate = result.diagnostics[0]
    with pytest.raises(ValueError, match="diagnostic ids"):
        ProteotypeMechanisticFeatureResult.model_validate(
            result.model_copy(update={"diagnostics": (duplicate, duplicate)}).model_dump(
                mode="python"
            )
        )


def test_result_status_and_digest_closures_reject_unsafe_states() -> None:
    result = construct_proteotype_mechanistic_features(request())
    with pytest.raises(ValueError, match="constructed result"):
        ProteotypeMechanisticFeatureResult.model_validate(
            result.model_copy(update={"feature_object": None}).model_dump(mode="python")
        )
    with pytest.raises(ValueError, match="abstained result"):
        ProteotypeMechanisticFeatureResult.model_validate(
            result.model_copy(
                update={"status": MechanisticConstructionStatus.ABSTAINED}
            ).model_dump(mode="python")
        )
    with pytest.raises(ValueError, match="result digest"):
        ProteotypeMechanisticFeatureResult.model_validate(
            result.model_copy(update={"result_digest": "sha256:" + "0" * 64}).model_dump(
                mode="python"
            )
        )
    assert canonical_request_digest(request()) == result.request_digest
    assert result_payload_digest(result) == result.result_digest
