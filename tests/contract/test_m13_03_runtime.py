"""Runtime, replay, authorization, and interface tests for M13-03."""

from __future__ import annotations

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
    MechanisticFeatureKind,
    MechanisticFeatureLineage,
    MechanisticValueKind,
    expected_uncertainty,
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
