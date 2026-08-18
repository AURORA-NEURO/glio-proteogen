"""Locked caller-declared M26-03 workflow fixtures.

The fixture deliberately binds M26-01 and M26-02 as media-only artifacts. It
does not import either upstream module, because M26-02 has no published ABI.
"""

from __future__ import annotations

from datetime import UTC, datetime

from glio_proteogen.contracts.m26_03 import (
    M2603_M2601_INPUT_MEDIA_TYPE,
    M2603_M2602_INPUT_MEDIA_TYPE,
    EnvironmentCapture,
    ExecuteProteinSubtypeWorkflowRequest,
    WorkflowDefinition,
    WorkflowStep,
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

FIXTURE_REQUEST_ID = "m2603-fixture-request"
FIXTURE_VERSION = "0.1.0"


def artifact(artifact_id: str, media_type: str) -> ArtifactReference:
    """Create an independently digested fixture artifact."""

    return ArtifactReference(
        artifact_id=artifact_id,
        version=FIXTURE_VERSION,
        digest=sha256_digest({"artifact_id": artifact_id, "media_type": media_type}),
        media_type=media_type,
    )


def evidence(
    reference: ArtifactReference,
    claim: str = "Locked M26-03 fixture evidence.",
) -> EvidenceReference:
    return EvidenceReference(reference=reference, role="evidence", claim=claim)


def context(request_id: str = FIXTURE_REQUEST_ID) -> ExecutionContext:
    control_evidence = artifact(
        "m2603-control-evidence", "application/vnd.glio-proteogen.control+json"
    )

    def decision(decision_id: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=decision_id,
            state=UpstreamDecisionState.ACCEPTED,
            policy_version=FIXTURE_VERSION,
            evidence=control_evidence,
        )

    return ExecutionContext(
        request_id=request_id,
        actor_id="m2603-fixture-actor",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("m2603-configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="m2603-identity",
                state=IdentityLineageState.RESOLVED,
                policy_version=FIXTURE_VERSION,
                binding_digest=control_evidence.digest,
                evidence=control_evidence,
            ),
            provenance=decision("m2603-provenance"),
            consent=ConsentReference(
                decision_id="m2603-consent",
                state=ConsentState.GRANTED,
                policy_version=FIXTURE_VERSION,
                evidence=control_evidence,
            ),
            quality=decision("m2603-quality"),
            support=decision("m2603-support"),
            intended_use=decision("m2603-intended-use"),
        ),
    )


def workflow() -> WorkflowDefinition:
    step_a_evidence = artifact("m2603-step-a-evidence", "application/json")
    step_b_evidence = artifact("m2603-step-b-evidence", "application/json")
    step_a = WorkflowStep(
        step_id="m2603.step.prepare",
        name="prepare locked feature bundle",
        version=FIXTURE_VERSION,
        container_digest=sha256_digest("m2603-container-prepare"),
        resource_class="cpu-small",
        max_retries=1,
        evidence=(evidence(step_a_evidence),),
    )
    step_b = WorkflowStep(
        step_id="m2603.step.execute",
        name="execute reproducible subtype workflow",
        version=FIXTURE_VERSION,
        dependencies=(step_a.step_id,),
        container_digest=sha256_digest("m2603-container-execute"),
        resource_class="cpu-medium",
        max_retries=2,
        evidence=(evidence(step_b_evidence),),
    )
    return WorkflowDefinition(
        workflow_id="m2603.locked-workflow",
        version=FIXTURE_VERSION,
        steps=(step_a, step_b),
        entry_step_ids=(step_a.step_id,),
        output_step_ids=(step_b.step_id,),
        workflow_digest=sha256_digest({"steps": (step_a, step_b)}),
        evidence=(evidence(step_a_evidence), evidence(step_b_evidence)),
    )


def environment() -> EnvironmentCapture:
    reference = artifact("m2603-environment-evidence", "application/json")
    return EnvironmentCapture(
        environment_id="m2603.locked-environment",
        version=FIXTURE_VERSION,
        container_runtime="oci://containerd/1.7",
        dependency_lock_digest=sha256_digest("m2603-lockfile"),
        operating_system="windows-2022",
        architecture="amd64",
        environment_digest=sha256_digest("m2603-environment"),
        evidence=(evidence(reference),),
    )


def build_request() -> ExecuteProteinSubtypeWorkflowRequest:
    m2601 = artifact("m2603-m2601-registry", M2603_M2601_INPUT_MEDIA_TYPE)
    m2602 = artifact("m2603-m2602-lineage", M2603_M2602_INPUT_MEDIA_TYPE)
    observed = artifact("m2603-observed-proteotype", "application/json")
    return ExecuteProteinSubtypeWorkflowRequest(
        request_id=FIXTURE_REQUEST_ID,
        context=context(),
        workflow=workflow(),
        environment=environment(),
        source_artifacts=(m2601, m2602, observed),
    )


def denied_request() -> ExecuteProteinSubtypeWorkflowRequest:
    request = build_request()
    references = request.context.references
    denied = references.support.model_copy(update={"state": UpstreamDecisionState.REJECTED})
    return request.model_copy(
        update={
            "context": request.context.model_copy(
                update={"references": references.model_copy(update={"support": denied})}
            )
        }
    )


__all__ = [
    "FIXTURE_REQUEST_ID",
    "artifact",
    "build_request",
    "context",
    "denied_request",
    "environment",
    "workflow",
]
