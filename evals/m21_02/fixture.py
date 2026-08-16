"""Frozen caller-declared M21-02 synthetic-truth scenarios."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from glio_proteogen.contracts.m21_02 import (
    M2102_M2101_INPUT_MEDIA_TYPE,
    FixtureKind,
    GenerateComplexActivitySyntheticTruthRequest,
    GenerationConfiguration,
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


def artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m2102.eval.{name}",
        version="0.1.0",
        digest="sha256:" + hashlib.sha256(f"m2102:{name}:{media_type}".encode()).hexdigest(),
        media_type=media_type,
    )


def context(request_id: str = "request.m2102.eval") -> ExecutionContext:
    control = artifact("control")
    accepted = UpstreamDecisionReference(
        decision_id="decision.m2102.eval.accepted",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=control,
    )
    return ExecutionContext(
        request_id=request_id,
        actor_id="actor.m2102.eval",
        occurred_at=datetime(2026, 8, 16, 20, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted,
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m2102.eval.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=control.digest,
                evidence=control,
            ),
            provenance=accepted,
            consent=ConsentReference(
                decision_id="decision.m2102.eval.consent",
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
        configuration_id="configuration.m2102.eval",
        version="0.1.0",
        generator_name="locked_m2102_fixture_generator",
        seed=20260816,
        requested_fixture_kinds=tuple(FixtureKind),
    )


def build_request() -> GenerateComplexActivitySyntheticTruthRequest:
    upstream = artifact("m2101-result", M2102_M2101_INPUT_MEDIA_TYPE)
    return GenerateComplexActivitySyntheticTruthRequest(
        request_id="request.m2102.eval",
        context=context(),
        upstream_result=upstream,
        configuration=configuration(),
        requested_case_count=10,
        source_artifacts=(upstream, artifact("generation-manifest")),
    )


def denied_request() -> GenerateComplexActivitySyntheticTruthRequest:
    request = build_request()
    denied = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    references = request.context.references.model_copy(update={"support": denied})
    return request.model_copy(
        update={"context": request.context.model_copy(update={"references": references})}
    )


__all__ = ["artifact", "build_request", "configuration", "context", "denied_request"]
