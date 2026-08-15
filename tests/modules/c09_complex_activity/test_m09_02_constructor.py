from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m09_01 import M0901_OUTPUT_MEDIA_TYPE
from glio_proteogen.contracts.m09_02 import (
    ConstructComplexActivityRepresentationRequest,
    FeatureLineage,
    FeatureSpecification,
    LeakageCheck,
    LeakageCheckStatus,
    RepresentationFeature,
    RepresentationPolicy,
    RepresentationTransformation,
    RepresentationTransformationKind,
    RepresentationValueKind,
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
from glio_proteogen.modules.c09_complex_activity import (
    m09_02_representation_feature_constructor as m0902,
)

_DIGEST = "sha256:" + ("a" * 64)


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"{name}." + ("b" * 32),
        version="1.0.0",
        digest=_DIGEST,
        media_type=media_type,
    )


def _context(*, consent: ConsentState = ConsentState.GRANTED) -> ExecutionContext:
    evidence = _artifact("control")
    accepted = UpstreamDecisionReference(
        decision_id="decision.accepted",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=evidence,
    )
    identity = IdentityLineageReference(
        decision_id="decision.identity",
        state=IdentityLineageState.RESOLVED,
        policy_version="1.0.0",
        binding_digest=_DIGEST,
        evidence=evidence,
    )
    consent_ref = ConsentReference(
        decision_id="decision.consent",
        state=consent,
        policy_version="1.0.0",
        evidence=evidence,
    )
    return ExecutionContext(
        request_id="request.m0902",
        actor_id="actor.test",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted,
            identity_lineage=identity,
            provenance=accepted,
            consent=consent_ref,
            quality=accepted,
            support=accepted,
            intended_use=accepted,
        ),
    )


def _request(*, marker: str | None = None) -> ConstructComplexActivityRepresentationRequest:
    source = _artifact("proteome", marker or "application/json")
    transform = RepresentationTransformation(
        sequence=1,
        kind=RepresentationTransformationKind.NORMALIZATION,
        name="locked-complex-scale",
        parameters_digest=_DIGEST,
    )
    lineage = FeatureLineage(
        feature_id="feature.complex.activity",
        source_artifacts=(source,),
        source_fields=("complex_abundance",),
        transformations=(transform,),
    )
    spec = FeatureSpecification(
        feature_id=lineage.feature_id,
        version="1.0.0",
        value_kind=RepresentationValueKind.SCALAR,
        unit="normalized-complex-activity",
        dimension=2,
        lineage=lineage,
    )
    return ConstructComplexActivityRepresentationRequest(
        request_id="request.m0902",
        context=_context(),
        formal_state_result=_artifact("state", M0901_OUTPUT_MEDIA_TYPE),
        feature_specs=(spec,),
        policy=RepresentationPolicy(
            policy_id="policy.locked",
            version="1.0.0",
            scaling_method=marker or "robust-median",
            mask_policy="observed-only",
            covariates=("batch", "platform"),
        ),
        source_artifacts=(source,),
    )


def test_constructor_is_deterministic_and_replay_bound() -> None:
    request = _request()
    engine = m0902.M0902RepresentationConstructor()
    first = engine.construct(request)
    second = engine.construct(request)
    assert first.canonical_bytes == second.canonical_bytes
    assert first.result.status.value == "constructed"
    assert first.result.features[0].lineage.feature_id == "feature.complex.activity"
    assert engine.verify(first.result, first.canonical_bytes)


@pytest.mark.parametrize("marker", ["missing", "unsupported", "ood", "not_evaluable"])
def test_unsupported_or_quality_markers_abstain_without_features(marker: str) -> None:
    result = m0902.M0902RepresentationConstructor().construct(_request(marker=marker)).result
    assert result.status.value == "abstained"
    assert result.features == ()
    assert result.support_decision.status.value == "unsupported"
    assert result.abstention_reason is not None


def test_leakage_failure_abstains_and_is_auditable() -> None:
    request = _request()
    policy = request.policy.model_copy(update={"mask_policy": "leakage_failure"})
    request = request.model_copy(update={"policy": policy})
    result = m0902.M0902RepresentationConstructor().construct(request).result
    assert result.status.value == "abstained"
    assert result.leakage_checks[0].status.value == "failed"
    assert result.leakage_checks[0].held_out_group == "held-out-group"


def test_tamper_is_rejected_without_mutating_result() -> None:
    built = m0902.M0902RepresentationConstructor().construct(_request())
    tampered = deepcopy(built.result.model_dump(mode="python"))
    tampered["features"][0]["values"] = (0.0, 0.0)
    assert not m0902.M0902RepresentationConstructor().verify(tampered, built.canonical_bytes)
    assert built.result.features[0].values != (0.0, 0.0)


def test_preflight_rejects_withheld_consent() -> None:
    request = _request().model_copy(update={"context": _context(consent=ConsentState.WITHHELD)})
    with pytest.raises(m0902.M0902AuthorizationError):
        m0902.M0902RepresentationConstructor().construct(request)


def test_contract_rejects_duplicate_lineage_and_mask_shape() -> None:
    source = _artifact("duplicate")
    transform = RepresentationTransformation(
        sequence=1,
        kind=RepresentationTransformationKind.NORMALIZATION,
        name="locked",
        parameters_digest=_DIGEST,
    )
    with pytest.raises(ValueError, match="source artifacts must be unique"):
        FeatureLineage(
            feature_id="feature.duplicate",
            source_artifacts=(source, source),
            source_fields=("field",),
            transformations=(transform,),
        )
    with pytest.raises(ValueError, match="unique ordered"):
        FeatureLineage(
            feature_id="feature.order",
            source_artifacts=(source,),
            source_fields=("field",),
            transformations=(transform, transform),
        )
    with pytest.raises(ValueError, match="source fields must be unique"):
        FeatureLineage(
            feature_id="feature.fields",
            source_artifacts=(source,),
            source_fields=("field", "field"),
            transformations=(transform,),
        )
    lineage = FeatureLineage(
        feature_id="feature.mask",
        source_artifacts=(source,),
        source_fields=("field",),
        transformations=(transform,),
    )
    with pytest.raises(ValueError, match="mask must be empty"):
        RepresentationFeature(
            feature_id=lineage.feature_id,
            value_kind=RepresentationValueKind.SCALAR,
            unit="unit",
            values=(0.2, 0.3),
            mask=(True,),
            lineage=lineage,
        )
    with pytest.raises(ValueError, match="retain at least"):
        RepresentationFeature(
            feature_id=lineage.feature_id,
            value_kind=RepresentationValueKind.SCALAR,
            unit="unit",
            values=(0.2, 0.3),
            mask=(False, False),
            lineage=lineage,
        )


def test_failed_leakage_check_requires_held_out_group() -> None:
    with pytest.raises(ValueError, match="held-out group"):
        LeakageCheck(
            check_id="leakage.failed",
            status=LeakageCheckStatus.FAILED,
            message="split is not isolated",
        )


def test_engine_verify_rejects_invalid_and_noncanonical_replay() -> None:
    engine = m0902.M0902RepresentationConstructor()
    built = engine.construct(_request())
    assert not engine.verify(object())
    assert not engine.verify(built.result, b"{}")
    assert not engine.verify(built.result, b"x" * (8 * 1024 * 1024 + 1))


def test_policy_and_constructor_defensive_error_paths() -> None:
    with pytest.raises(ValueError, match="covariates must be unique"):
        RepresentationPolicy(
            policy_id="policy.duplicate",
            version="1.0.0",
            scaling_method="median",
            mask_policy="observed",
            covariates=("batch", "batch"),
        )
    context = _context()
    rejected = context.references.quality.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    denied = context.model_copy(
        update={"references": context.references.model_copy(update={"quality": rejected})}
    )
    with pytest.raises(m0902.M0902AuthorizationError):
        m0902.M0902RepresentationConstructor().construct(
            _request().model_copy(update={"context": denied})
        )


def test_leakage_unknown_abstains_and_public_service_delegates() -> None:
    request = _request().model_copy(
        update={"policy": _request().policy.model_copy(update={"mask_policy": "leakage_unknown"})}
    )
    service = m0902.M0902Service()
    built = service.execute(request)
    assert built.result.status.value == "abstained"
    assert built.result.leakage_checks[0].status.value == "not_evaluable"
    assert service.verify(built.result, built.canonical_bytes)
    assert (
        m0902.construct_complex_activity_representation(_request()).result.status.value
        == "constructed"
    )


def test_built_result_seal_rejects_digest_and_bytes_drift() -> None:
    built = m0902.M0902RepresentationConstructor().construct(_request())
    with pytest.raises(m0902.M0902InputError, match="digest"):
        m0902.BuiltM0902Result(
            result=built.result.model_copy(update={"result_digest": "sha256:" + ("0" * 64)}),
            canonical_bytes=built.canonical_bytes,
        )
    with pytest.raises(m0902.M0902InputError, match="canonical"):
        m0902.BuiltM0902Result(result=built.result, canonical_bytes=b"{}")
