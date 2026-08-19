"""Adversarial runtime, replay, and plugin tests for provisional M14-03."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from json import dumps
from typing import Any

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m14_03 import (
    M1403_M1402_INPUT_MEDIA_TYPE,
    ConstructProteinSubtypeMechanisticFeaturesRequest,
    MechanisticConstructionStatus,
    MechanisticFeature,
    MechanisticFeatureConfiguration,
    MechanisticFeatureKind,
    MechanisticFeatureLineage,
    MechanisticFindingCode,
    MechanisticRelation,
    MechanisticRelationKind,
    MechanisticValueKind,
    ProteinSubtypeMechanisticFeatureResult,
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
from glio_proteogen.modules.c14_microenvironment_protein_deconvolution import (
    m14_03_mechanistic_feature_constructor as m1403,
)

_FEATURE_COUNT = 7
_RELATION_COUNT = 6
_CONTROL_COUNT = 7


def _artifact(label: str, *, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m1403.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1403": label}),
        media_type=media_type,
    )


def _context(
    *,
    quality: UpstreamDecisionState = UpstreamDecisionState.ACCEPTED,
) -> ExecutionContext:
    return ExecutionContext(
        request_id="context.m1403.request",
        actor_id="actor.m1403.fixture",
        occurred_at=datetime(2026, 8, 15, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=UpstreamDecisionReference(
                decision_id="decision.m1403.config",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=_artifact("control-config"),
            ),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m1403.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest({"identity": "fixture"}),
                evidence=_artifact("control-identity"),
            ),
            provenance=UpstreamDecisionReference(
                decision_id="decision.m1403.provenance",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=_artifact("control-provenance"),
            ),
            consent=ConsentReference(
                decision_id="decision.m1403.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("control-consent"),
            ),
            quality=UpstreamDecisionReference(
                decision_id="decision.m1403.quality",
                state=quality,
                policy_version="1.0.0",
                evidence=_artifact("control-quality"),
            ),
            support=UpstreamDecisionReference(
                decision_id="decision.m1403.support",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=_artifact("control-support"),
            ),
            intended_use=UpstreamDecisionReference(
                decision_id="decision.m1403.use",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=_artifact("control-use"),
            ),
        ),
    )


def _request(
    *,
    model_family: str = "deterministic_metadata_replay",
    quality: UpstreamDecisionState = UpstreamDecisionState.ACCEPTED,
) -> ConstructProteinSubtypeMechanisticFeaturesRequest:
    return ConstructProteinSubtypeMechanisticFeaturesRequest(
        request_id="request.m1403.fixture",
        context=_context(quality=quality),
        upstream_result=_artifact("m1402-result", media_type=M1403_M1402_INPUT_MEDIA_TYPE),
        configuration=MechanisticFeatureConfiguration(
            configuration_id="configuration.m1403.fixture",
            version="1.0.0",
            model_family=model_family,
            transformation_ids=("transform.m1403.normalize", "transform.m1403.project"),
            stoichiometry_reference=_artifact("stoichiometry"),
            negative_control_artifacts=(_artifact("negative-control"),),
            evidence=(),
        ),
        source_artifacts=(_artifact("source-alpha"), _artifact("source-beta")),
    )


def test_constructs_all_declared_feature_kinds_and_replays() -> None:
    service = m1403.M1403Service()
    request = _request()
    result = service.construct(request)

    assert result.status is MechanisticConstructionStatus.CONSTRUCTED
    assert result.feature_object is not None
    assert len(result.feature_object.features) == _FEATURE_COUNT
    assert len(result.feature_object.relations) == _RELATION_COUNT
    assert {feature.kind for feature in result.feature_object.features} == set(
        MechanisticFeatureKind
    )
    assert all(
        feature.value_kind is MechanisticValueKind.CATEGORICAL
        for feature in result.feature_object.features
    )
    assert all(
        feature.category is not None and feature.category.startswith("caller_declared:")
        for feature in result.feature_object.features
    )
    assert result.human_review_required is True
    assert service.verify(result).model_dump(mode="json") == result.model_dump(mode="json")


def test_unsupported_configuration_abstains_without_feature_object() -> None:
    result = m1403.M1403Service().construct(
        _request(model_family="scientific_model_not_frozen")
    )

    assert result.status is MechanisticConstructionStatus.ABSTAINED
    assert result.feature_object is None
    assert result.findings == (MechanisticFindingCode.UPSTREAM_UNSUPPORTED,)
    assert result.abstention_reason is not None


def test_denied_control_fails_before_configuration_traversal() -> None:
    with pytest.raises(m1403.M1403AuthorizationError):
        m1403.M1403Service().construct(_request(quality=UpstreamDecisionState.REJECTED))
    with pytest.raises(m1403.M1403AuthorizationError):
        m1403.preflight_m1403_authorization({})


def test_plugin_requires_validated_token_and_supports_strict_json() -> None:
    plugin = m1403.M1403Plugin(m1403.M1403Service())
    request = _request()
    token = plugin.validate(request.model_dump_json())
    assert plugin.run(token).status is MechanisticConstructionStatus.CONSTRUCTED
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]


def test_plugin_json_preflights_authorization_before_nested_contract_validation() -> None:
    plugin = m1403.M1403Plugin(m1403.M1403Service())
    payload = _request(quality=UpstreamDecisionState.REJECTED).model_dump(mode="json")
    configuration = payload["configuration"]
    assert isinstance(configuration, dict)
    configuration["unexpected"] = True

    with pytest.raises(m1403.M1403AuthorizationError):
        plugin.validate(dumps(payload))


def test_unknown_fields_and_wrong_upstream_media_type_reject() -> None:
    payload = _request().model_dump(mode="python")
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        m1403.M1403Service().validate_request(payload)
    wrong_upstream = _request().model_dump(mode="python")
    wrong_upstream["upstream_result"] = _artifact("wrong", media_type="application/json")
    with pytest.raises(ValidationError, match="M14-02"):
        m1403.M1403Service().validate_request(wrong_upstream)


def test_result_tampering_and_contract_relation_boundaries_fail_closed() -> None:
    service = m1403.M1403Service()
    result = service.construct(_request())
    forged = result.model_copy(update={"result_digest": "sha256:" + "f" * 64})
    with pytest.raises(m1403.M1403ReplayVerificationError):
        service.verify(forged)

    lineage = MechanisticFeatureLineage(
        feature_id="feature.m1403.one",
        source_artifacts=(_artifact("lineage"),),
        claim="Caller-declared feature.",
    )
    feature = MechanisticFeature(
        feature_id="feature.m1403.one",
        version="1.0.0",
        kind=MechanisticFeatureKind.PATHWAY,
        value_kind=MechanisticValueKind.CATEGORICAL,
        unit="caller_declared",
        category="caller_declared:pathway",
        lineage=lineage,
    )
    with pytest.raises(ValueError, match="self-loop"):
        MechanisticRelation(
            relation_id="relation.m1403.self",
            source_feature_id=feature.feature_id,
            target_feature_id=feature.feature_id,
            kind=MechanisticRelationKind.PARTICIPATES,
        )


def test_public_result_is_provenance_bound_and_claims_ceiling_is_visible() -> None:
    result = m1403.M1403Service().construct(_request())
    assert result.provenance.module_id == "GLIO-PROTEOGEN-M14-03"
    assert len(result.provenance.control_decisions) == _CONTROL_COUNT
    assert all(
        item.state in {"accepted", "resolved", "granted"}
        for item in result.provenance.control_decisions
    )
    limitation_text = " ".join(item.statement for item in result.limitations)
    assert "do not infer biological mechanism" in limitation_text
    assert "kinase" not in result.model_dump_json().lower()


def test_mapping_reconstruction_and_invalid_candidate_paths_fail_closed() -> None:
    service = m1403.M1403Service()
    request = _request()
    payload = request.model_dump(mode="python")
    assert service.construct(payload).status is MechanisticConstructionStatus.CONSTRUCTED
    with pytest.raises(TypeError, match="strict request model or mapping"):
        service.validate_request(42)

    class _Candidate:
        context = _context()

    with pytest.raises(TypeError, match="strict request model or mapping"):
        m1403.M1403MechanisticFeatureEngine().construct(_Candidate())

    class _ExplodingMapping(Mapping[str, Any]):
        def __getitem__(self, key: str) -> object:
            raise RuntimeError(key)

        def __iter__(self) -> Iterator[str]:
            return iter(())

        def __len__(self) -> int:
            return 0

        def get(self, key: str, _default: object = None) -> object:
            raise RuntimeError(key)

    with pytest.raises(m1403.M1403AuthorizationError):
        m1403.preflight_m1403_authorization(_ExplodingMapping())


def test_duplicate_evidence_and_negative_controls_are_not_silently_accepted() -> None:
    request = _request().model_copy(
        update={
            "source_artifacts": (_artifact("control-config"),),
        }
    )
    result = m1403.M1403Service().construct(request)
    assert len(result.evidence) < len(result.request.source_artifacts) + 10

    duplicate_configuration = request.configuration.model_copy(
        update={
            "negative_control_artifacts": (
                _artifact("same-negative"),
                _artifact("same-negative"),
            )
        }
    )
    duplicate = request.model_copy(update={"configuration": duplicate_configuration})
    abstained = m1403.M1403Service().construct(duplicate)
    assert abstained.status is MechanisticConstructionStatus.ABSTAINED


def test_plugin_descriptor_model_validation_and_service_replay_modes() -> None:
    service = m1403.M1403Service()
    plugin = m1403.M1403Plugin(service)
    request = _request()
    token = plugin.validate(request)
    result = plugin.run(token)
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M14-03"
    assert plugin.verify(result, replay=False).result_id == result.result_id


def test_replay_mismatch_is_detected_after_valid_digest_reconstruction() -> None:
    service = m1403.M1403Service()
    result = service.construct(_request())
    altered = result.model_copy(update={"human_review_required": False})
    constructed = ProteinSubtypeMechanisticFeatureResult.model_construct(
        **altered.__dict__
    )
    altered = altered.model_copy(update={"result_digest": result_payload_digest(constructed)})
    with pytest.raises(m1403.M1403ReplayVerificationError):
        service.verify(altered)
