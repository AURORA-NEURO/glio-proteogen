"""Deep contract/runtime/interface coverage for provisional M27-03."""

# HTTP status assertions intentionally use the protocol constants directly.
# ruff: noqa: PLR2004,TRY003

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.contracts.m27_03 import (
    M2703_M2702_INPUT_MEDIA_TYPE,
    ComplexActivityPipelineResult,
    ExecutionPolicy,
    ExecutionStatus,
    OrchestrateComplexActivityPipelineRequest,
    PipelineStatus,
    WorkflowDAG,
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodeKind,
)
from glio_proteogen.contracts.m27_03.canonical import (
    canonical_request_digest,
    execution_id_for_request_digest,
    package_id_for_request_digest,
    result_id_for_request_digest,
    result_payload_digest,
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
from glio_proteogen.modules.c27_complex_activity.m27_03_reproducible_pipeline_orchestrator import (
    M2703Engine,
    M2703Plugin,
    M2703ReplayError,
    M2703Service,
    cli_app,
    create_app,
    execute_complex_activity_pipeline,
    preflight_m2703_authorization,
)
from glio_proteogen.modules.c27_complex_activity.m27_03_reproducible_pipeline_orchestrator import (
    engine as runtime,
)

if TYPE_CHECKING:
    from pathlib import Path


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


def _request(
    *, support: UpstreamDecisionState = UpstreamDecisionState.ACCEPTED
) -> OrchestrateComplexActivityPipelineRequest:
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
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
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


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("manifest_digest", "manifest digest"),
        ("reproducibility_digest", "reproducibility digest"),
    ],
)
def test_self_rehashed_result_rejects_forged_package_digest(field: str, message: str) -> None:
    result = M2703Engine().execute(_request())
    assert result.result_package is not None
    forged_package = result.result_package.model_copy(update={field: _digest(903)})
    payload = result.model_copy(update={"result_package": forged_package}).model_dump(mode="python")
    payload["result_digest"] = result_payload_digest(payload)

    with pytest.raises(ValidationError, match=message):
        ComplexActivityPipelineResult.model_validate(payload, strict=True)


def test_self_rehashed_result_rejects_forged_package_dependency_references() -> None:
    result = M2703Engine().execute(_request())
    assert result.result_package is not None
    package = result.result_package
    forged_source = package.artifact_references[1].model_copy(update={"digest": _digest(904)})
    forged_package = package.model_copy(
        update={"artifact_references": (package.artifact_references[0], forged_source)}
    )
    payload = result.model_copy(update={"result_package": forged_package}).model_dump(mode="python")
    payload["result_digest"] = result_payload_digest(payload)

    with pytest.raises(ValidationError, match="exact request dependencies"):
        ComplexActivityPipelineResult.model_validate(payload, strict=True)


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
                WorkflowEdge(
                    edge_id="a",
                    source_node_id="entry",
                    target_node_id="exit",
                    evidence=(_evidence(210),),
                ),
                WorkflowEdge(
                    edge_id="b",
                    source_node_id="exit",
                    target_node_id="entry",
                    evidence=(_evidence(211),),
                ),
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


def test_replay_rejects_self_rehashed_semantic_mutation() -> None:
    engine = M2703Engine()
    result = engine.execute(_request())
    mutated_support = result.support_decision.model_copy(
        update={"rationale": "caller-rehashed semantic mutation"}
    )
    mutated = result.model_copy(update={"support_decision": mutated_support})
    rehashed = mutated.model_copy(update={"result_digest": result_payload_digest(mutated)})

    with pytest.raises(M2703ReplayError, match="deterministic replay mismatch"):
        engine.verify(rehashed)


def test_replay_opt_out_cannot_accept_self_rehashed_semantic_mutation() -> None:
    engine = M2703Engine()
    result = engine.execute(_request())
    mutated_support = result.support_decision.model_copy(
        update={"rationale": "caller-rehashed mutation with replay disabled"}
    )
    mutated = result.model_copy(update={"support_decision": mutated_support})
    rehashed = mutated.model_copy(update={"result_digest": result_payload_digest(mutated)})

    with pytest.raises(M2703ReplayError, match="cannot be disabled"):
        engine.verify(rehashed, replay=False)


def test_fastapi_exposes_schema_and_sanitizes_bad_json() -> None:
    client = TestClient(create_app())
    response = client.get("/v1/modules/M27-03/schemas/request")
    assert response.status_code == 200
    assert response.json()["x-glio-contract"]["provisionalAbi"] is True
    bad = client.post("/v1/modules/M27-03/validate", content=b"{bad")
    assert bad.status_code == 422
    assert "traceback" not in bad.text.lower()


def test_fastapi_validate_execute_verify_and_unknown_schema() -> None:
    request = _request()
    client = TestClient(create_app())
    body = request.model_dump_json()
    assert client.get("/v1/modules/M27-03/schemas/nope").status_code == 404
    validated = client.post("/v1/modules/M27-03/validate", content=body)
    assert validated.status_code == 200
    executed = client.post("/v1/modules/M27-03/execute", content=body)
    assert executed.status_code == 200
    result = executed.json()
    verified = client.post("/v1/modules/M27-03/verify", json={"result": result})
    assert verified.status_code == 200
    assert verified.json()["verified"] is True
    malformed = client.post("/v1/modules/M27-03/verify", json={"result": {"bad": True}})
    assert malformed.status_code == 422


def test_fastapi_streams_bodies_and_bounds_result_envelopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request()
    client = TestClient(create_app())

    def fail_body(_request: object) -> bytes:
        raise AssertionError("FastAPI adapter must consume the bounded request stream")

    monkeypatch.setattr("starlette.requests.Request.body", fail_body)
    validated = client.post("/v1/modules/M27-03/validate", content=request.model_dump_json())
    assert validated.status_code == 200

    monkeypatch.setattr(
        "glio_proteogen.modules.c27_complex_activity.m27_03_reproducible_pipeline_orchestrator.api.M2703_MAX_CANONICAL_RESULT_BYTES",
        32,
    )
    oversized = client.post("/v1/modules/M27-03/verify", content=b"{}" + (b" " * 40))
    assert oversized.status_code == 422
    assert oversized.json()["detail"] == "request exceeds byte limit"


def test_fastapi_sanitizes_route_service_errors() -> None:
    class FailingService(M2703Service):
        def validate_request(self, _candidate: object) -> OrchestrateComplexActivityPipelineRequest:
            raise ValueError("internal detail")

        def execute(self, _request: object) -> ComplexActivityPipelineResult:
            raise ValueError("internal detail")

    client = TestClient(create_app(FailingService()))
    body = _request().model_dump_json()
    assert client.get("/v1/modules/M27-03/schemas").status_code == 200
    assert client.post("/v1/modules/M27-03/validate", content=body).status_code == 422
    assert client.post("/v1/modules/M27-03/execute", content=body).status_code == 422
    assert client.post("/v1/modules/M27-03/verify", content=b"[]").status_code == 422
    assert client.post("/v1/modules/M27-03/verify", content=b"{bad").status_code == 422


def test_cli_schema_validate_execute_verify_and_no_overwrite(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_bytes(_request().model_dump_json().encode())
    runner = CliRunner()
    schema = runner.invoke(cli_app, ["export-schema", "request"])
    assert schema.exit_code == 0
    validated = runner.invoke(cli_app, ["validate", str(request_path)])
    assert validated.exit_code == 0
    executed = runner.invoke(cli_app, ["execute", str(request_path), "--output", str(result_path)])
    assert executed.exit_code == 0
    verified = runner.invoke(cli_app, ["verify", str(result_path)])
    assert verified.exit_code == 0
    overwrite = runner.invoke(cli_app, ["execute", str(request_path), "--output", str(result_path)])
    assert overwrite.exit_code != 0
    unknown = runner.invoke(cli_app, ["export-schema", "unknown"])
    assert unknown.exit_code != 0


def test_cli_rejects_invalid_inputs_and_reports_abstention(tmp_path: Path) -> None:
    runner = CliRunner()
    bad_request = tmp_path / "bad-request.json"
    bad_request.write_text("{bad", encoding="utf-8")
    bad_result = tmp_path / "bad-result.json"
    bad_result.write_text("{bad", encoding="utf-8")
    assert runner.invoke(cli_app, ["validate", str(bad_request)]).exit_code != 0
    assert runner.invoke(cli_app, ["execute", str(bad_request)]).exit_code != 0
    assert runner.invoke(cli_app, ["verify", str(bad_result)]).exit_code != 0
    schema_path = tmp_path / "schema.json"
    assert (
        runner.invoke(cli_app, ["export-schema", "request", "--output", str(schema_path)]).exit_code
        == 0
    )
    rejected = tmp_path / "rejected.json"
    rejected.write_bytes(
        _request(support=UpstreamDecisionState.REJECTED).model_dump_json().encode()
    )
    assert runner.invoke(cli_app, ["execute", str(rejected)]).exit_code == 1


def test_contract_rejects_self_edge_unknown_and_duplicate_edges() -> None:
    request = _request()
    first, second = request.workflow.nodes
    with pytest.raises(ValidationError, match="endpoints must be distinct"):
        WorkflowEdge(
            edge_id="self",
            source_node_id="entry",
            target_node_id="entry",
            evidence=(_evidence(220),),
        )
    with pytest.raises(ValidationError, match="node ids must be unique"):
        WorkflowDAG(
            workflow_id="duplicate-nodes",
            version="1.0.0",
            nodes=(first, first),
            entry_node_id="entry",
            exit_node_id="entry",
            evidence=(_evidence(221),),
        )
    edge = WorkflowEdge(
        edge_id="edge", source_node_id="entry", target_node_id="exit", evidence=(_evidence(222),)
    )
    with pytest.raises(ValidationError, match="duplicate source"):
        WorkflowDAG(
            workflow_id="duplicate-edges",
            version="1.0.0",
            nodes=(first, second),
            edges=(edge, edge.model_copy(update={"edge_id": "edge-2"})),
            entry_node_id="entry",
            exit_node_id="exit",
            evidence=(_evidence(223),),
        )


def test_contract_rejects_unknown_edge_and_unreachable_node() -> None:
    request = _request()
    first, second = request.workflow.nodes
    with pytest.raises(ValidationError, match="unknown node"):
        WorkflowDAG(
            workflow_id="unknown-edge",
            version="1.0.0",
            nodes=(first, second),
            edges=(
                WorkflowEdge(
                    edge_id="bad",
                    source_node_id="entry",
                    target_node_id="missing",
                    evidence=(_evidence(224),),
                ),
            ),
            entry_node_id="entry",
            exit_node_id="exit",
            evidence=(_evidence(225),),
        )
    with pytest.raises(ValidationError, match="entry"):
        WorkflowDAG(
            workflow_id="unreachable",
            version="1.0.0",
            nodes=(first, second),
            entry_node_id="missing",
            exit_node_id="exit",
            evidence=(_evidence(226),),
        )


def test_preflight_mapping_and_public_entry_point() -> None:
    request = _request()
    preflight_m2703_authorization(request.model_dump(mode="json"))
    with pytest.raises(ValueError, match="malformed"):
        preflight_m2703_authorization({"context": {"references": None}})
    assert execute_complex_activity_pipeline(request).status is PipelineStatus.EXECUTED


def test_engine_safe_failure_catches_scheduler_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise runtime.M2703EvaluationError("synthetic scheduler failure")

    monkeypatch.setattr(runtime, "_execution", fail)
    result = M2703Engine().execute(_request())
    assert result.status is PipelineStatus.ABSTAINED


def test_canonical_identity_helpers_reject_non_digest_inputs() -> None:
    digest = canonical_request_digest(_request())
    assert result_id_for_request_digest(digest).startswith("m2703.result.")
    assert execution_id_for_request_digest(digest).startswith("m2703.execution.")
    assert package_id_for_request_digest(digest).startswith("m2703.package.")
    for helper in (
        result_id_for_request_digest,
        execution_id_for_request_digest,
        package_id_for_request_digest,
    ):
        with pytest.raises(ValueError, match="canonical sha256"):
            helper("not-a-digest")


def test_plugin_descriptor_and_all_parse_paths() -> None:
    request = _request()
    plugin = M2703Plugin()
    descriptor = plugin.descriptor()
    assert descriptor.module_id == "GLIO-PROTEOGEN-M27-03"
    result = plugin.run(plugin.validate(request.model_dump_json()))
    assert plugin.verify(result.model_dump_json()).result_digest == result.result_digest
    with pytest.raises(TypeError):
        plugin.run(plugin.validate(request).request)  # type: ignore[arg-type]


def test_service_mapping_and_engine_validation_errors() -> None:
    request = _request()
    service = M2703Service()
    assert (
        service.validate_request(request.model_dump(mode="json")).request_id == request.request_id
    )
    result = service.execute(request)
    assert service.verify(result.model_dump(mode="json")).result_digest == result.result_digest
    with pytest.raises(ValueError, match="object"):
        service.validate_request(b"[]")
    with pytest.raises(ValueError, match="invalid"):
        service.verify({"result": "invalid"}, replay=False)
    with pytest.raises(ValueError, match="invalid"):
        M2703Engine().validate_request({"invalid": True})


def test_result_closure_rejects_mismatched_bindings() -> None:
    result = M2703Engine().execute(_request())
    assert result.execution_record is not None
    assert result.result_package is not None
    execution = result.execution_record
    package = result.result_package
    tampered = (
        ("request digest", {"request_digest": _digest(901)}),
        ("result id", {"result_id": "m2703.result." + "f" * 64}),
        (
            "execution id",
            {"execution_record": execution.model_copy(update={"execution_id": "wrong"})},
        ),
        ("workflow", {"execution_record": execution.model_copy(update={"workflow_id": "other"})}),
        ("nodes", {"execution_record": execution.model_copy(update={"completed_node_ids": ()})}),
        (
            "package execution",
            {"result_package": package.model_copy(update={"execution_id": "wrong"})},
        ),
        ("package id", {"result_package": package.model_copy(update={"package_id": "wrong"})}),
        (
            "environment",
            {"result_package": package.model_copy(update={"environment_digest": _digest(902)})},
        ),
        ("output", {"execution_record": execution.model_copy(update={"output_digest": None})}),
        ("review", {"human_review_required": True}),
    )
    for _label, update in tampered:
        with pytest.raises(ValidationError, match=r".*"):
            ComplexActivityPipelineResult.model_validate(result.model_copy(update=update))
    rejected = M2703Engine().execute(_request(support=UpstreamDecisionState.REJECTED))
    with pytest.raises(ValidationError):
        ComplexActivityPipelineResult.model_validate(
            rejected.model_copy(
                update={
                    "support_decision": rejected.support_decision.model_copy(
                        update={"status": SupportStatus.SUPPORTED}
                    )
                }
            )
        )
