"""Frozen, caller-declared M24-02 synthetic truth fixture."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from glio_proteogen.contracts.m24_02 import (
    M2402_M2401_INPUT_MEDIA_TYPE,
    FixtureKind,
    GenerateBiomarkerPanelSyntheticTruthRequest,
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


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="0.1.0",
        digest="sha256:" + hashlib.sha256(name.encode()).hexdigest(),
        media_type=media_type,
    )


def _context(request_id: str) -> ExecutionContext:
    evidence = _artifact("m2402.fixture.controls")
    accepted = UpstreamDecisionReference(
        decision_id="m2402.fixture.accepted",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=evidence,
    )
    return ExecutionContext(
        request_id=request_id,
        actor_id="m2402.fixture.actor",
        occurred_at=datetime(2026, 8, 16, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted,
            identity_lineage=IdentityLineageReference(
                decision_id="m2402.fixture.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest="sha256:" + "1" * 64,
                evidence=evidence,
            ),
            provenance=accepted,
            consent=ConsentReference(
                decision_id="m2402.fixture.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=evidence,
            ),
            quality=accepted,
            support=accepted,
            intended_use=accepted,
        ),
    )


def build_request() -> GenerateBiomarkerPanelSyntheticTruthRequest:
    """Return the locked five-kind, ten-case fixture."""

    request_id = "m2402.fixture.request"
    upstream = _artifact("m2401.sensitivity", M2402_M2401_INPUT_MEDIA_TYPE)
    configuration = GenerationConfiguration(
        configuration_id="m2402.fixture.configuration",
        version="1.0.0",
        generator_name="m2402-locked-fixture-generator",
        seed=2402,
        requested_fixture_kinds=tuple(FixtureKind),
        evidence=(),
    )
    return GenerateBiomarkerPanelSyntheticTruthRequest(
        request_id=request_id,
        context=_context(request_id),
        upstream_result=upstream,
        configuration=configuration,
        requested_case_count=10,
        source_artifacts=(upstream, _artifact("m2402.fixture.policy")),
    )


def denied_request() -> GenerateBiomarkerPanelSyntheticTruthRequest:
    request = build_request()
    rejected = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    context = request.context.model_copy(
        update={"references": request.context.references.model_copy(update={"support": rejected})}
    )
    return request.model_copy(update={"context": context})


__all__ = ["build_request", "denied_request"]
