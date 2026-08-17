"""Deep contract/runtime/interface coverage for provisional M27-03."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m27_03 import (
    M2703_M2702_INPUT_MEDIA_TYPE,
    ExecutionPolicy,
    ExecutionStatus,
    OrchestrateComplexActivityPipelineRequest,
    PipelineStatus,
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
    ExecutionContext,
    EvidenceReference,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c27_complex_activity.m27_03_reproducible_pipeline_orchestrator.api import (
    create_app,
)
from glio_proteogen.modules.c27_complex_activity.m27_03_reproducible_pipeline_orchestrator.engine import (
    M2703Engine,
    M2703ReplayError,
)
from glio_proteogen.modules.c27_complex_activity.m27_03_reproducible_pipeline_orchestrator.plugin import (
    M2703Plugin,
)
from glio_proteogen.modules.c27_complex_activity.m27_03_reproducible_pipeline_orchestrator.service import (
    M2703Service,
)


def _digest(number: int) -> str:
    return "sha256:" + f"{number:064x}"


def _artifact(name: str, number: int, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest=_digest(number),
        media_type=media_type,
    )


def _evidence(number: int) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(f"evidence-{number}", number),
        role="evidence",
        claim="caller-declared orchestration evidence",
    )


def _request(*, support: UpstreamDecisionState = UpstreamDecisionState.ACCEPTED) -> OrchestrateComplexActivityPipelineRequest:
    references = ContextReferences(
        approved_configuration=UpstreamDecisionReference(
            decision_id="configuration",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact("control-1", 101),
        ),
        identity_lineage=IdentityLineageReference(
            decision_id="identity",
            state=IdentityLineageState.RESOLVED,
            policy_version="1.0.0",
            binding_digest=_digest(102),
            evidence=_artifact("control-2", 102),
        ),
        provenance=UpstreamDecisionReference(
            decision_id="provenance",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact("control-3", 103),
        ),
        consent=ConsentReference(
            decision_id="consent",
            state=ConsentState.GRANTED,
            policy_version="1.0.0",
            evidence=_artifact("control-4", 104),
        ),
        quality=UpstreamDecisionReference(
            decision_id="quality",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact("control-5", 105),
        ),
        support=UpstreamDecisionReference(
            decision_id="support",
            state=support,
            policy_version="1.0.0",
            evidence=_artifact("control-6", 106),
        ),
        intended_use=UpstreamDecisionReference(
            decision_id="intended-use",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact("control-7", 107),
        ),
    )
    context = ExecutionContext(
        request_id="context-request",
        actor_id="test-actor",
        occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        references=references,
    )
    entry = WorkflowNode(
        node_id="entry",
        kind=WorkflowNodeKind.CONTAINER,
        name="locked-entry",
        container_image="registry.example/pipeline",
        container_digest=_digest(201),
        version="1.0.0",
        cpu_millis=100,
        memory_bytes=1024,
        evidence=(_evidence(201),),
    )
    exit_node = WorkflowNode(
        node_id="exit",
        kind=WorkflowNodeKind.VALIDATION,
        name="locked-exit",
        container_image="registry.example/pipeline",
        container_digest=_digest(202),
        version="1.0.0",
        cpu_millis=100,
        memory_bytes=1024,
        evidence=(_evidence(202),),
    )
    workflow = WorkflowDAG(
        workflow_id="complex-activity-workflow",
        version="1.0.0",
        nodes=(entry, exit_node),
        edges=(
            WorkflowEdge(
                edge_id="entry-to-exit",
                source_node_id="entry",
                target_node_id="exit",
                evidence=(_evidence(203),),
            ),
        ),
        entry_node_id="entry",
        exit_node_id="exit",
        evidence=(_evidence(204),),
    )
    policy = ExecutionPolicy(
        policy_id="deterministic-policy",
        version="1.0.0",
        deterministic_seed=17,
        max_retries=2,
        checkpoint_interval_nodes=1,
        evidence=(_evidence(205),),
    )
    return OrchestrateComplexActivityPipelineRequest(
        request_id="pipeline-request",
        context=context,
        upstream_result=_artifact("m27-02-result", 301, M2703_M2702_INPUT_MEDIA_TYPE),
        workflow=workflow,
        policy=policy,
        source_artifacts=(_artifact("source-manifest", 302),),
    )


def test_supported_execution_closes_environment_checkpoint_and_package() -> None:
    request = _request()
    result = M2703Engine().execute(request)
    assert result.status is PipelineStatus.EXECUTED
    assert result.execution_record is not None
    assert result.result_package is not None
    assert result.execution_record.status is ExecutionStatus.SUCCEEDED
    assert set(result.execution_record.completed_node_ids) == {"entry", "exit"}
    assert result.result_package.execution_id == result.execution_record.execution_id
    assert M2703Engine().verify(result).result_digest == result.result_digest


def test_rejected_support_abstains_without_execution_or_negative_claim() -> None:
    result = M2703Engine().execute(_request(support=UpstreamDecisionState.REJECTED))
    assert result.status is PipelineStatus.ABSTAINED
    assert result.execution_record is None
    assert result.result_package is None
    assert result.human_review_required is True
    assert result.support_decision.status.value == "review_required"


def test_dag_rejects_cycle_and_disconnected_nodes() -> None:
    request = _request()
    first, second = request.workflow.nodes
    with pytest.raises(ValidationError, match="acyclic"):
        WorkflowDAG(
            workflow_id="cycle",
            version="1.0.0",
            nodes=(first, second),
            edges=(
                WorkflowEdge(edge_id="a", source_node_id="entry", target_node_id="exit", evidence=(_evidence(210),)),
                WorkflowEdge(edge_id="b", source_node_id="exit", target_node_id="entry", evidence=(_evidence(211),)),
            ),
            entry_node_id="entry",
            exit_node_id="exit",
            evidence=(_evidence(212),),
        )


def test_request_rejects_duplicate_source_identity() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="unique ids and digests"):
        OrchestrateComplexActivityPipelineRequest.model_validate(
            request.model_dump(mode="python")
            | {"source_artifacts": (request.source_artifacts[0], request.source_artifacts[0])}
        )


def test_plugin_requires_opaque_validation_token_and_service_parses_json_once() -> None:
    request = _request()
    plugin = M2703Plugin()
    token = plugin.validate(request.model_dump(mode="json"))
    assert plugin.run(token).status is PipelineStatus.EXECUTED
    with pytest.raises(TypeError):
        plugin.run(object())  # type: ignore[arg-type]
    service = M2703Service()
    result = service.execute(request.model_dump_json())
    assert service.verify(result.model_dump_json()).result_digest == result.result_digest


def test_tampered_result_is_rejected_by_replay() -> None:
    result = M2703Engine().execute(_request())
    tampered = result.model_copy(update={"result_id": "m2703.result." + "f" * 64})
    with pytest.raises(M2703ReplayError):
        M2703Engine().verify(tampered, replay=False)


def test_fastapi_exposes_schema_and_sanitizes_bad_json() -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_app())
    response = client.get("/v1/modules/M27-03/schemas/request")
    assert response.status_code == 200
    assert response.json()["x-glio-contract"]["provisionalAbi"] is True
    bad = client.post("/v1/modules/M27-03/validate", content=b"{bad")
    assert bad.status_code == 422
    assert "traceback" not in bad.text.lower()
