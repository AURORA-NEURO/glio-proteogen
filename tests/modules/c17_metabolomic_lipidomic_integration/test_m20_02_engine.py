"""Runtime, replay, and safe-boundary tests for M20-02."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m20_02 import (
    M2002_M2001_INPUT_MEDIA_TYPE,
    AlignmentConfiguration,
    AlignmentDimension,
    AlignmentObservation,
    AlignmentObservationStatus,
    AlignmentStatus,
    AlignProteinSubtypeSourcesRequest,
)
from glio_proteogen.contracts.m20_02.canonical import result_payload_digest
from glio_proteogen.kernel.canonical import sha256_digest
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
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration.m20_02_cross_source_alignment_reconciliation import (  # noqa: E501
    M2002AuthorizationError,
    M2002Engine,
    M2002Plugin,
    M2002ReplayError,
    M2002Service,
    preflight_m2002_authorization,
)

_WHEN = datetime(2026, 1, 2, tzinfo=UTC)


def _artifact(label: str, *, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m2002": label}),
        media_type=media_type,
    )


def _context() -> ExecutionContext:
    accepted = UpstreamDecisionState.ACCEPTED
    return ExecutionContext(
        request_id="request.m2002",
        actor_id="actor.test",
        occurred_at=_WHEN,
        references=ContextReferences(
            approved_configuration=UpstreamDecisionReference(
                decision_id="decision.configuration",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("configuration"),
            ),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("identity"),
                evidence=_artifact("identity"),
            ),
            provenance=UpstreamDecisionReference(
                decision_id="decision.provenance",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("provenance"),
            ),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=UpstreamDecisionReference(
                decision_id="decision.quality",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("quality"),
            ),
            support=UpstreamDecisionReference(
                decision_id="decision.support",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("support"),
            ),
            intended_use=UpstreamDecisionReference(
                decision_id="decision.intended",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("intended"),
            ),
        ),
    )


def _evidence(label: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(label), role="evidence", claim="caller-declared alignment evidence"
    )


def _configuration() -> AlignmentConfiguration:
    return AlignmentConfiguration(
        configuration_id="configuration.m2002",
        version="1.0.0",
        required_dimensions=tuple(AlignmentDimension),
        evidence=(_evidence("configuration"),),
    )


def _observation(
    dimension: AlignmentDimension,
    *,
    status: AlignmentObservationStatus = AlignmentObservationStatus.ALIGNED,
) -> AlignmentObservation:
    return AlignmentObservation(
        observation_id=f"observation.{dimension.value}",
        dimension=dimension,
        source_ids=("artifact.source-a", "artifact.source-b"),
        reference_value="locked-reference",
        observed_values=("declared-a", "declared-b"),
        status=status,
        rationale="caller-declared values are compared under the locked configuration",
        evidence=(_evidence(f"observation.{dimension.value}"),),
    )


def _request(
    *,
    status: AlignmentObservationStatus = AlignmentObservationStatus.ALIGNED,
) -> AlignProteinSubtypeSourcesRequest:
    return AlignProteinSubtypeSourcesRequest(
        request_id="request.m2002",
        context=_context(),
        upstream_result=_artifact("upstream", media_type=M2002_M2001_INPUT_MEDIA_TYPE),
        source_artifacts=(_artifact("source-a"), _artifact("source-b")),
        observations=tuple(
            _observation(dimension, status=status) for dimension in AlignmentDimension
        ),
        configuration=_configuration(),
    )


def test_aligned_resolution_is_deterministic_and_replayable() -> None:
    request = _request()
    engine = M2002Engine()
    first = engine.resolve(request)
    second = engine.resolve(request.model_dump(mode="python"))

    assert first.status is AlignmentStatus.ALIGNED
    assert first.aligned_bundle is not None
    assert first.result_digest == second.result_digest
    assert engine.replay(first) == first


def test_conflicted_dimension_abstains_and_preserves_finding() -> None:
    result = M2002Engine().resolve(_request(status=AlignmentObservationStatus.CONFLICTED))

    assert result.status is AlignmentStatus.ABSTAINED
    assert result.aligned_bundle is None
    assert result.human_review_required is True
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.findings[0].code.value == "dimension_conflict"


def test_replay_rejects_tampered_result() -> None:
    engine = M2002Engine()
    result = engine.resolve(_request())
    with pytest.raises(M2002ReplayError, match="identifier"):
        engine.replay(result.model_copy(update={"result_id": "result.tampered"}))
    with pytest.raises(M2002ReplayError, match="payload digest"):
        engine.replay(result.model_copy(update={"result_digest": "sha256:" + "0" * 64}))
    semantic = result.model_copy(update={"human_review_required": not result.human_review_required})
    semantic = semantic.model_copy(update={"result_digest": result_payload_digest(semantic)})
    with pytest.raises(M2002ReplayError, match="deterministic replay"):
        engine.replay(semantic)


def test_preflight_rejects_missing_or_unsafe_control() -> None:
    raw = _request().model_dump(mode="python")
    raw["context"]["references"] = None
    with pytest.raises(M2002AuthorizationError, match="seven upstream controls"):
        preflight_m2002_authorization(raw)

    rejected = _request().context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    context = _request().context.model_copy(
        update={
            "references": _request().context.references.model_copy(update={"support": rejected})
        }
    )
    with pytest.raises(M2002AuthorizationError, match="control support"):
        preflight_m2002_authorization(_request().model_copy(update={"context": context}))


def test_service_and_plugin_share_strict_boundary() -> None:
    request = _request()
    service = M2002Service()
    plugin = M2002Plugin()
    assert service.validate_request(request) == request
    assert plugin.validate_request(request) == request
    result = plugin.run(request)
    assert plugin.verify(result) == result
    assert plugin.descriptor.external_content_traversal is False
    assert plugin.descriptor.all_omics_fusion is False
    assert plugin.descriptor.kinase_activity is False
    assert plugin.descriptor.treatment_recommendation is False

