"""Self-contained synthetic request fixture for the M20-02 evaluation lane."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

from glio_proteogen.contracts.m20_02 import (
    M2002_M2001_INPUT_MEDIA_TYPE,
    AlignmentConfiguration,
    AlignmentDimension,
    AlignmentObservation,
    AlignmentObservationStatus,
    AlignProteinSubtypeSourcesRequest,
)
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
    UpstreamDecisionReference,
    UpstreamDecisionState,
)

_SYNTHETIC_OCCURRED_AT: Final = datetime(2026, 1, 2, tzinfo=UTC)


def _artifact(label: str, *, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.synthetic.m2002.{label}",
        version="1.0.0",
        digest=sha256_digest({"synthetic_m2002_fixture": label}),
        media_type=media_type,
    )


def _context() -> ExecutionContext:
    accepted = UpstreamDecisionState.ACCEPTED
    return ExecutionContext(
        request_id="request.synthetic.m2002",
        actor_id="actor.synthetic.evaluator",
        occurred_at=_SYNTHETIC_OCCURRED_AT,
        references=ContextReferences(
            approved_configuration=UpstreamDecisionReference(
                decision_id="decision.synthetic.m2002.configuration",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("configuration"),
            ),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.synthetic.m2002.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest({"synthetic_m2002_fixture": "identity-binding"}),
                evidence=_artifact("identity"),
            ),
            provenance=UpstreamDecisionReference(
                decision_id="decision.synthetic.m2002.provenance",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("provenance"),
            ),
            consent=ConsentReference(
                decision_id="decision.synthetic.m2002.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=UpstreamDecisionReference(
                decision_id="decision.synthetic.m2002.quality",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("quality"),
            ),
            support=UpstreamDecisionReference(
                decision_id="decision.synthetic.m2002.support",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("support"),
            ),
            intended_use=UpstreamDecisionReference(
                decision_id="decision.synthetic.m2002.intended-use",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("intended-use"),
            ),
        ),
    )


def _evidence(label: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(label),
        role="evidence",
        claim="synthetic caller-declared alignment evidence",
    )


def _configuration() -> AlignmentConfiguration:
    return AlignmentConfiguration(
        configuration_id="configuration.synthetic.m2002",
        version="1.0.0",
        required_dimensions=tuple(AlignmentDimension),
        evidence=(_evidence("configuration-evidence"),),
    )


def _observation(
    dimension: AlignmentDimension,
    *,
    status: AlignmentObservationStatus,
) -> AlignmentObservation:
    return AlignmentObservation(
        observation_id=f"observation.synthetic.m2002.{dimension.value}",
        dimension=dimension,
        source_ids=("artifact.synthetic.m2002.source-a", "artifact.synthetic.m2002.source-b"),
        reference_value="synthetic-locked-reference",
        observed_values=("synthetic-declared-a", "synthetic-declared-b"),
        status=status,
        rationale="synthetic values are compared under the locked evaluation configuration",
        evidence=(_evidence(f"observation-{dimension.value}"),),
    )


def build_synthetic_request(
    *,
    status: AlignmentObservationStatus = AlignmentObservationStatus.ALIGNED,
) -> AlignProteinSubtypeSourcesRequest:
    """Build one deterministic, non-patient M20-02 request for evaluation."""

    return AlignProteinSubtypeSourcesRequest(
        request_id="request.synthetic.m2002",
        context=_context(),
        upstream_result=_artifact("upstream", media_type=M2002_M2001_INPUT_MEDIA_TYPE),
        source_artifacts=(_artifact("source-a"), _artifact("source-b")),
        observations=tuple(
            _observation(dimension, status=status) for dimension in AlignmentDimension
        ),
        configuration=_configuration(),
    )


__all__ = ["build_synthetic_request"]
