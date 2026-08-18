"""Frozen caller-declared M23-02 synthetic-truth evaluation fixture."""

from __future__ import annotations

from datetime import UTC, datetime

from glio_proteogen.contracts.m23_02 import (
    M2302_M2301_INPUT_MEDIA_TYPE,
    FixtureKind,
    GenerateVariantPeptideSyntheticTruthRequest,
    GenerationConfiguration,
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


def artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    """Return a deterministic fixture artifact with an explicit media type."""

    return ArtifactReference(
        artifact_id=f"artifact.m2302.eval.{name}",
        version="0.1.0",
        digest=sha256_digest(f"m2302:{name}:{media_type}"),
        media_type=media_type,
    )


def _evidence(name: str) -> EvidenceReference:
    return EvidenceReference(
        reference=artifact(name),
        role="evidence",
        claim="Frozen M23-02 synthetic-truth evaluation evidence.",
    )


def context(request_id: str = "request.m2302.eval") -> ExecutionContext:
    control = artifact("control")
    accepted = UpstreamDecisionReference(
        decision_id="decision.m2302.eval.accepted",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=control,
    )
    return ExecutionContext(
        request_id=request_id,
        actor_id="actor.m2302.eval",
        occurred_at=datetime(2026, 8, 16, 20, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted,
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m2302.eval.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=control.digest,
                evidence=control,
            ),
            provenance=accepted,
            consent=ConsentReference(
                decision_id="decision.m2302.eval.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=control,
            ),
            quality=accepted,
            support=accepted,
            intended_use=accepted,
        ),
    )


def configuration() -> GenerationConfiguration:
    return GenerationConfiguration(
        configuration_id="configuration.m2302.eval",
        version="0.1.0",
        generator_name="locked_m2302_fixture_generator",
        seed=20260816,
        requested_fixture_kinds=tuple(FixtureKind),
        evidence=(_evidence("configuration"),),
    )


def build_request() -> GenerateVariantPeptideSyntheticTruthRequest:
    """Return the frozen ten-case fixture spanning all five fixture kinds."""

    upstream = artifact("m2301-result", M2302_M2301_INPUT_MEDIA_TYPE)
    return GenerateVariantPeptideSyntheticTruthRequest(
        request_id="request.m2302.eval",
        context=context(),
        upstream_result=upstream,
        configuration=configuration(),
        requested_case_count=10,
        source_artifacts=(upstream, artifact("generation-manifest")),
    )


def denied_request() -> GenerateVariantPeptideSyntheticTruthRequest:
    """Return a fixture denied by the caller-declared support control."""

    request = build_request()
    denied = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    references = request.context.references.model_copy(update={"support": denied})
    return request.model_copy(
        update={"context": request.context.model_copy(update={"references": references})}
    )


__all__ = ["artifact", "build_request", "configuration", "context", "denied_request"]
