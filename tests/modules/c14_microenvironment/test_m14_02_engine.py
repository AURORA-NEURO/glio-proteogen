"""M14-02 runtime, replay, authorization, and safety tests."""

# ruff: noqa: PLR2004, TRY003

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m14_02 import (
    ContextDimension,
    ContextObservation,
    ContextObservationStatus,
    ContextStratificationStatus,
    StratifierConfiguration,
    StratifierPolicy,
    StratifyProteinSubtypeContextRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
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
from glio_proteogen.modules.c14_microenvironment.m14_02_context_subtype_stratifier import (
    M1402AuthorizationError,
    M1402ContextStratifier,
    M1402ReplayVerificationError,
    preflight_context_authorization,
)

_WHEN = datetime(2026, 1, 1, tzinfo=UTC)


def _artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1402": label}),
        media_type=media_type,
    )


def _evidence(label: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(label),
        role="evidence",
        claim="Caller-declared M14-02 context evidence.",
    )


def _controls(*, accepted: bool = True) -> ContextReferences:
    decision = UpstreamDecisionState.ACCEPTED if accepted else UpstreamDecisionState.REJECTED
    identity = IdentityLineageState.RESOLVED if accepted else IdentityLineageState.UNRESOLVED
    consent = ConsentState.GRANTED if accepted else ConsentState.WITHHELD
    return ContextReferences(
        approved_configuration=UpstreamDecisionReference(
            decision_id="decision.configuration",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.configuration"),
        ),
        identity_lineage=IdentityLineageReference(
            decision_id="decision.identity",
            state=identity,
            policy_version="1.0.0",
            binding_digest=sha256_digest("identity"),
            evidence=_artifact("control.identity"),
        ),
        provenance=UpstreamDecisionReference(
            decision_id="decision.provenance",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.provenance"),
        ),
        consent=ConsentReference(
            decision_id="decision.consent",
            state=consent,
            policy_version="1.0.0",
            evidence=_artifact("control.consent"),
        ),
        quality=UpstreamDecisionReference(
            decision_id="decision.quality",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.quality"),
        ),
        support=UpstreamDecisionReference(
            decision_id="decision.support",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.support"),
        ),
        intended_use=UpstreamDecisionReference(
            decision_id="decision.intended",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.intended"),
        ),
    )


def _request(
    method: str = "curated_rule",
    *,
    accepted: bool = True,
    observation_status: ContextObservationStatus = ContextObservationStatus.SUPPORTED,
    proxy_value: str | None = None,
) -> StratifyProteinSubtypeContextRequest:
    dimensions = tuple(ContextDimension)
    observations = tuple(
        ContextObservation(
            observation_id=f"observation.{dimension.value}",
            dimension=dimension,
            value=proxy_value if proxy_value is not None else f"value-{dimension.value}",
            normalized_value=(
                None
                if observation_status is ContextObservationStatus.UNRESOLVED
                else f"normalized-{dimension.value}"
            ),
            status=observation_status,
            source_artifact=_artifact(f"observation.{dimension.value}"),
            evidence=(_evidence(f"observation.{dimension.value}"),),
        )
        for dimension in dimensions
    )
    configuration = StratifierConfiguration(
        configuration_id="configuration.m1402",
        version="1.0.0",
        method=method,
        model_reference=_artifact("model"),
        evidence=(_evidence("configuration"),),
    )
    return StratifyProteinSubtypeContextRequest(
        request_id="request.m1402",
        context=ExecutionContext(
            request_id="request.m1402",
            actor_id="actor.test",
            occurred_at=_WHEN,
            references=_controls(accepted=accepted),
        ),
        microenvironment_deconvolution_result=_artifact(
            "microenvironment", "application/vnd.glio-proteogen.m14-01+json"
        ),
        policy=StratifierPolicy(
            required_dimensions=dimensions,
            configuration=configuration,
        ),
        observations=observations,
        source_artifacts=(_artifact("source"),),
    )


def test_supported_context_profile_is_deterministic_and_replayable() -> None:
    result = M1402ContextStratifier().infer(_request())
    assert result.status is ContextStratificationStatus.STRATIFIED
    assert result.context_profile is not None
    assert result.applicable_mechanisms
    assert result.parent_target == "protein_subtype"
    assert result.emits_parent is False
    assert result.uncertainty.measurement.probability == 0.9
    assert M1402ContextStratifier().verify(result) == result


@pytest.mark.parametrize(
    "method",
    ["bayesian_graph", "state_space", "mechanistic", "foundation_assisted", "enrichment"],
)
def test_declared_architecture_methods_are_supported(method: str) -> None:
    result = M1402ContextStratifier().infer(_request(method))
    assert result.status is ContextStratificationStatus.STRATIFIED


def test_unsupported_context_abstains_without_negative_finding() -> None:
    result = M1402ContextStratifier().infer(_request("unknown-method"))
    assert result.status is ContextStratificationStatus.ABSTAINED
    assert result.context_profile is None
    assert result.applicable_mechanisms == ()
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.human_review_required
    assert result.findings


@pytest.mark.parametrize(
    "status", [ContextObservationStatus.CONFLICTED, ContextObservationStatus.UNRESOLVED]
)
def test_conflicted_and_unresolved_observations_quarantine(
    status: ContextObservationStatus,
) -> None:
    result = M1402ContextStratifier().infer(_request(observation_status=status))
    assert result.status is ContextStratificationStatus.ABSTAINED
    assert result.context_profile is None


def test_proxy_and_authorization_boundaries_fail_closed() -> None:
    proxy = M1402ContextStratifier().infer(_request(proxy_value="kinase activity"))
    assert proxy.status is ContextStratificationStatus.ABSTAINED
    with pytest.raises(M1402AuthorizationError):
        M1402ContextStratifier().infer(_request(accepted=False))

    class Hostile:
        @property
        def context(self) -> object:
            raise RuntimeError("must not traverse opaque content")

    with pytest.raises(M1402AuthorizationError):
        preflight_context_authorization(Hostile())


def test_replay_tamper_and_canonical_bytes_are_rejected() -> None:
    engine = M1402ContextStratifier()
    result = engine.infer(_request())
    assert canonical_json_bytes(result)
    with pytest.raises(M1402ReplayVerificationError):
        engine.verify(result.model_copy(update={"result_digest": sha256_digest("tampered")}))
    assert engine.verify(result, replay=False) == result


def test_request_duplicate_observation_ids_are_rejected() -> None:
    request = _request().model_dump(mode="python")
    request["observations"] = (request["observations"][0], request["observations"][0])
    with pytest.raises(ValueError, match="observation ids"):
        StratifyProteinSubtypeContextRequest.model_validate(request, strict=True)
