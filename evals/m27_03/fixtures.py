"""Frozen synthetic caller-declared M27-03 scenarios."""

from __future__ import annotations

from datetime import UTC, datetime

from glio_proteogen.contracts.m27_03 import (
    M2703_M2702_INPUT_MEDIA_TYPE,
    ExecutionPolicy,
    OrchestrateComplexActivityPipelineRequest,
    WorkflowDAG,
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodeKind,
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
    UpstreamDecisionReference,
    UpstreamDecisionState,
)


def digest(number: int) -> str:
    return "sha256:" + f"{number:064x}"


def artifact(name: str, number: int, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest=digest(number),
        media_type=media_type,
    )


def evidence(number: int) -> EvidenceReference:
    return EvidenceReference(
        reference=artifact(f"evidence-{number}", number),
        role="evidence",
        claim="locked synthetic orchestration evidence",
    )


def request(
    *, support: UpstreamDecisionState = UpstreamDecisionState.ACCEPTED
) -> OrchestrateComplexActivityPipelineRequest:
    refs = ContextReferences(
        approved_configuration=UpstreamDecisionReference(
            decision_id="configuration",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=artifact("control-1", 101),
        ),
        identity_lineage=IdentityLineageReference(
            decision_id="identity",
            state=IdentityLineageState.RESOLVED,
            policy_version="1.0.0",
            binding_digest=digest(102),
            evidence=artifact("control-2", 102),
        ),
        provenance=UpstreamDecisionReference(
            decision_id="provenance",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=artifact("control-3", 103),
        ),
        consent=ConsentReference(
            decision_id="consent",
            state=ConsentState.GRANTED,
            policy_version="1.0.0",
            evidence=artifact("control-4", 104),
        ),
        quality=UpstreamDecisionReference(
            decision_id="quality",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=artifact("control-5", 105),
        ),
        support=UpstreamDecisionReference(
            decision_id="support",
            state=support,
            policy_version="1.0.0",
            evidence=artifact("control-6", 106),
        ),
        intended_use=UpstreamDecisionReference(
            decision_id="intended-use",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=artifact("control-7", 107),
        ),
    )
    context = ExecutionContext(
        request_id="context-request",
        actor_id="evaluator",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=refs,
    )
    nodes = (
        WorkflowNode(
            node_id="entry",
            kind=WorkflowNodeKind.CONTAINER,
            name="locked-entry",
            container_image="registry.example/pipeline",
            container_digest=digest(201),
            version="1.0.0",
            cpu_millis=100,
            memory_bytes=1024,
            evidence=(evidence(201),),
        ),
        WorkflowNode(
            node_id="exit",
            kind=WorkflowNodeKind.VALIDATION,
            name="locked-exit",
            container_image="registry.example/pipeline",
            container_digest=digest(202),
            version="1.0.0",
            cpu_millis=100,
            memory_bytes=1024,
            evidence=(evidence(202),),
        ),
    )
    workflow = WorkflowDAG(
        workflow_id="complex-activity-workflow",
        version="1.0.0",
        nodes=nodes,
        edges=(
            WorkflowEdge(
                edge_id="entry-to-exit",
                source_node_id="entry",
                target_node_id="exit",
                evidence=(evidence(203),),
            ),
        ),
        entry_node_id="entry",
        exit_node_id="exit",
        evidence=(evidence(204),),
    )
    policy = ExecutionPolicy(
        policy_id="deterministic-policy",
        version="1.0.0",
        deterministic_seed=17,
        max_retries=2,
        checkpoint_interval_nodes=1,
        evidence=(evidence(205),),
    )
    return OrchestrateComplexActivityPipelineRequest(
        request_id="pipeline-request",
        context=context,
        upstream_result=artifact("m27-02-result", 301, M2703_M2702_INPUT_MEDIA_TYPE),
        workflow=workflow,
        policy=policy,
        source_artifacts=(artifact("source-manifest", 302),),
    )
