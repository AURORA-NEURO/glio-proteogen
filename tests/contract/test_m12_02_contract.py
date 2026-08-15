"""Deep contract and runtime tests for provisional M12-02."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m12_02 import (
    M1202_MODULE_ID,
    ApplicableMechanism,
    ContextDimension,
    ContextObservation,
    ContextObservationStatus,
    ContextStratifierConfiguration,
    ContextStratifierPolicy,
    MechanismApplicability,
    StratifierStatus,
    StratifyBiomarkerPanelContextRequest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c12_driver_to_protein_consequence import (
    m12_02_context_subtype_stratifier as m1202_runtime,
)

_DIGEST = "sha256:" + ("a" * 64)
_OTHER_DIGEST = "sha256:" + ("b" * 64)
_WHEN = datetime(2026, 1, 1, tzinfo=UTC)
_DIMENSION_COUNT = 8
M1202ContextAuthorizationError = m1202_runtime.M1202ContextAuthorizationError
M1202ContextEngine = m1202_runtime.M1202ContextEngine
M1202ReplayVerificationError = m1202_runtime.M1202ReplayVerificationError


def _artifact(name: str, digest: str = _DIGEST) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest=digest,
        media_type="application/json",
    )


def _controls(
    *, support: UpstreamDecisionState = UpstreamDecisionState.ACCEPTED
) -> ContextReferences:
    return ContextReferences(
        approved_configuration=UpstreamDecisionReference(
            decision_id="decision.config",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact("evidence.config"),
        ),
        identity_lineage=IdentityLineageReference(
            decision_id="decision.identity",
            state=IdentityLineageState.RESOLVED,
            policy_version="1.0.0",
            binding_digest=_OTHER_DIGEST,
            evidence=_artifact("evidence.identity"),
        ),
        provenance=UpstreamDecisionReference(
            decision_id="decision.provenance",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact("evidence.provenance"),
        ),
        consent=ConsentReference(
            decision_id="decision.consent",
            state=ConsentState.GRANTED,
            policy_version="1.0.0",
            evidence=_artifact("evidence.consent"),
        ),
        quality=UpstreamDecisionReference(
            decision_id="decision.quality",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact("evidence.quality"),
        ),
        support=UpstreamDecisionReference(
            decision_id="decision.support",
            state=support,
            policy_version="1.0.0",
            evidence=_artifact("evidence.support"),
        ),
        intended_use=UpstreamDecisionReference(
            decision_id="decision.intended",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact("evidence.intended"),
        ),
    )


def _observation(
    dimension: ContextDimension,
    value: str,
    index: int,
    *,
    status: ContextObservationStatus = ContextObservationStatus.SUPPORTED,
) -> ContextObservation:
    evidence = (
        EvidenceReference(
            reference=_artifact(f"evidence.observation.{index}"),
            role="evidence",
            claim=f"Declared {dimension.value} observation",
        ),
    )
    return ContextObservation(
        observation_id=f"observation.{index}",
        dimension=dimension,
        value=value,
        normalized_value=value.lower(),
        status=status,
        source_artifact=_artifact(f"observation.source.{index}"),
        evidence=evidence,
    )


def _request(
    observations: tuple[ContextObservation, ...] | None = None,
    *,
    support: UpstreamDecisionState = UpstreamDecisionState.ACCEPTED,
) -> StratifyBiomarkerPanelContextRequest:
    selected = observations or tuple(
        _observation(dimension, value, index)
        for index, (dimension, value) in enumerate(
            (
                (ContextDimension.DISEASE_CLASS, "glioma"),
                (ContextDimension.SUBTYPE, "mesenchymal"),
                (ContextDimension.AGE, "adult"),
                (ContextDimension.TERRITORY, "brain"),
                (ContextDimension.TREATMENT_ERA, "modern"),
                (ContextDimension.SPECIMEN, "tumor"),
                (ContextDimension.PLATFORM, "mass-spectrometry"),
                (ContextDimension.BIOLOGICAL_CONTEXT, "immune"),
            ),
            start=1,
        )
    )
    configuration = ContextStratifierConfiguration(
        configuration_id="configuration.m1202",
        version="1.0.0",
        method="curated_context_rules",
        model_reference=_artifact("model.m1202"),
        evidence=(
            EvidenceReference(
                reference=_artifact("evidence.configuration"),
                role="evidence",
                claim="Locked context stratifier configuration",
            ),
        ),
    )
    return StratifyBiomarkerPanelContextRequest(
        request_id="request.m1202.1",
        context=ExecutionContext(
            request_id="request.m1202.1",
            actor_id="actor.test",
            occurred_at=_WHEN,
            references=_controls(support=support),
        ),
        driver_consequence_result=_artifact("upstream.driver_consequence"),
        policy=ContextStratifierPolicy(
            required_dimensions=tuple(ContextDimension),
            configuration=configuration,
        ),
        observations=selected,
        source_artifacts=(_artifact("source.context"),),
    )


def test_supported_context_profile_and_mechanisms_are_typed() -> None:
    result = M1202ContextEngine().stratify(_request())

    assert result.status is StratifierStatus.STRATIFIED
    assert result.context_profile is not None
    assert len(result.context_profile.observations) == _DIMENSION_COUNT
    assert result.support_decision.status is SupportStatus.SUPPORTED
    assert result.provenance.module_id == M1202_MODULE_ID
    assert any(
        mechanism.applicability is MechanismApplicability.APPLICABLE
        for mechanism in result.applicable_mechanisms
    )
    assert result.emits_parent is False


def test_unknown_context_does_not_become_negative_mechanism() -> None:
    observations = tuple(
        _observation(
            dimension,
            "unrecognized-context" if dimension is ContextDimension.BIOLOGICAL_CONTEXT else value,
            index,
        )
        for index, (dimension, value) in enumerate(
            (
                (ContextDimension.DISEASE_CLASS, "glioma"),
                (ContextDimension.SUBTYPE, "unknown-subtype"),
                (ContextDimension.AGE, "adult"),
                (ContextDimension.TERRITORY, "brain"),
                (ContextDimension.TREATMENT_ERA, "modern"),
                (ContextDimension.SPECIMEN, "tumor"),
                (ContextDimension.PLATFORM, "mass-spectrometry"),
                (ContextDimension.BIOLOGICAL_CONTEXT, "immune"),
            ),
            start=1,
        )
    )
    result = M1202ContextEngine().stratify(_request(observations))

    assert result.status is StratifierStatus.STRATIFIED
    assert all(
        mechanism.applicability is not MechanismApplicability.NOT_SUPPORTED
        for mechanism in result.applicable_mechanisms
    )


def test_missing_dimension_abstains_without_profile_or_mechanisms() -> None:
    observations = tuple(
        observation
        for observation in _request().observations
        if observation.dimension is not ContextDimension.PLATFORM
    )
    result = M1202ContextEngine().stratify(_request(observations))

    assert result.status is StratifierStatus.ABSTAINED
    assert result.context_profile is None
    assert result.applicable_mechanisms == ()
    assert result.human_review_required is True
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED


def test_conflicting_observations_are_preserved_and_abstain() -> None:
    base = _request().observations
    conflict = _observation(ContextDimension.SUBTYPE, "proneural", 99)
    result = M1202ContextEngine().stratify(_request((*base, conflict)))

    assert result.status is StratifierStatus.ABSTAINED
    assert result.context_profile is None
    assert any("conflict" in finding.finding_id for finding in result.findings)


def test_limited_observation_abstains_without_negative_conversion() -> None:
    observations = tuple(
        _observation(
            observation.dimension,
            observation.value,
            index,
            status=(
                ContextObservationStatus.LIMITED
                if observation.dimension is ContextDimension.TERRITORY
                else observation.status
            ),
        )
        for index, observation in enumerate(_request().observations, start=1)
    )
    result = M1202ContextEngine().stratify(_request(observations))

    assert result.status is StratifierStatus.ABSTAINED
    assert result.context_profile is None
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED


def test_control_denial_fails_before_request_materialization() -> None:
    with pytest.raises(M1202ContextAuthorizationError):
        M1202ContextEngine().stratify(_request(support=UpstreamDecisionState.REJECTED))


def test_replay_verification_and_tamper_detection() -> None:
    engine = M1202ContextEngine()
    result = engine.stratify(_request())

    assert engine.verify(result).model_dump(mode="json") == result.model_dump(mode="json")
    with pytest.raises(M1202ReplayVerificationError):
        engine.verify(result.model_copy(update={"result_digest": _OTHER_DIGEST}))


def test_unknown_mechanism_contract_is_not_negative() -> None:
    mechanism = ApplicableMechanism(
        mechanism_id="mechanism.unknown",
        label="Unknown context mechanism",
        applicability=MechanismApplicability.UNKNOWN,
        rationale="No support-domain match was declared.",
    )
    assert mechanism.applicability is MechanismApplicability.UNKNOWN
