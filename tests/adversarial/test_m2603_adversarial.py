"""Adversarial closure for M26-03 boundaries and immutable evidence."""

from __future__ import annotations

from typing import Any, cast

import pytest
from evals.m26_03.fixture import build_request, denied_request
from pydantic import ValidationError

from glio_proteogen.contracts.m26_03 import (
    ExecutionAttempt,
    ExecutionRecord,
    ExecutionStatus,
    StepStatus,
    WorkflowDefinition,
)
from glio_proteogen.kernel.strict_json import StrictJsonError
from glio_proteogen.modules.c21_reference_material.m26_03_reproducible_pipeline_orchestrator import (  # noqa: E501
    M2603AuthorizationError,
    M2603Engine,
    M2603EvaluationError,
    M2603Plugin,
    M2603ReplayError,
    M2603Service,
    ValidatedM2603Request,
)


def test_workflow_rejects_duplicate_and_unknown_graph_boundaries() -> None:
    request = build_request()
    duplicate_entry = request.workflow.model_copy(
        update={"entry_step_ids": (request.workflow.entry_step_ids[0],) * 2}
    )
    with pytest.raises(M2603EvaluationError):
        M2603Service().execute(request.model_copy(update={"workflow": duplicate_entry}))
    unknown_output = request.workflow.model_copy(update={"output_step_ids": ("unknown-step",)})
    with pytest.raises(M2603EvaluationError):
        M2603Service().execute(request.model_copy(update={"workflow": unknown_output}))


def test_request_rejects_context_source_and_media_binding_tampering() -> None:
    request = build_request()
    mismatched_context = request.context.model_copy(update={"request_id": "different-request"})
    with pytest.raises(M2603EvaluationError):
        M2603Service().execute(request.model_copy(update={"context": mismatched_context}))

    duplicate_source = request.model_copy(
        update={"source_artifacts": (*request.source_artifacts, request.source_artifacts[0])}
    )
    with pytest.raises(M2603EvaluationError):
        M2603Service().execute(duplicate_source)
    renamed_source = request.source_artifacts[0].model_copy(
        update={"artifact_id": "m2603-renamed-source"}
    )
    with pytest.raises(M2603EvaluationError):
        M2603Service().execute(
            request.model_copy(
                update={"source_artifacts": (*request.source_artifacts, renamed_source)}
            )
        )
    rehashed_source = request.source_artifacts[0].model_copy(
        update={"digest": "sha256:" + "f" * 64}
    )
    with pytest.raises(M2603EvaluationError):
        M2603Service().execute(
            request.model_copy(
                update={"source_artifacts": (*request.source_artifacts, rehashed_source)}
            )
        )

    no_m2601 = tuple(item for item in request.source_artifacts if "m26-01" not in item.media_type)
    with pytest.raises(M2603EvaluationError):
        M2603Service().execute(request.model_copy(update={"source_artifacts": no_m2601}))


def test_completed_record_requires_every_step_and_checkpoint() -> None:
    engine = M2603Engine()
    result = engine.execute(build_request())
    assert result.execution_record is not None
    incomplete = result.execution_record.model_copy(
        update={"attempts": (result.execution_record.attempts[0],)}
    )
    tampered = result.model_copy(update={"execution_record": incomplete})
    with pytest.raises(M2603ReplayError):
        engine.verify(tampered, replay=False)


def test_result_finding_and_evidence_identity_cannot_be_duplicated() -> None:
    engine = M2603Engine()
    result = engine.execute(build_request())
    duplicate_finding = result.model_copy(update={"findings": result.findings * 2})
    with pytest.raises(M2603ReplayError):
        engine.verify(duplicate_finding, replay=False)
    duplicate_evidence = result.model_copy(update={"evidence": result.evidence * 2})
    with pytest.raises(M2603ReplayError):
        engine.verify(duplicate_evidence, replay=False)


def test_plugin_token_is_opaque_and_forged_token_is_rejected() -> None:
    plugin = M2603Plugin()
    request = build_request()
    token = plugin.validate(request)
    assert plugin.run(token).status is ExecutionStatus.COMPLETED
    with pytest.raises(TypeError):
        plugin.run(cast("Any", request))
    forged = ValidatedM2603Request(request=token.request, _seal=object())
    with pytest.raises(TypeError):
        plugin.run(forged)


def test_plugin_rejects_foreign_token_and_nested_request_mutation() -> None:
    request = build_request()
    first = M2603Plugin()
    second = M2603Plugin()
    token = first.validate(request)
    with pytest.raises(TypeError):
        second.run(token)
    object.__setattr__(token.request, "request_id", "m2603.tampered")
    with pytest.raises(TypeError):
        first.run(token)


def test_strict_json_rejects_duplicate_keys_and_non_object_inputs() -> None:
    service = M2603Service()
    with pytest.raises((StrictJsonError, ValueError)):
        service.validate_request(b'{"request_id":"a","request_id":"b"}')
    with pytest.raises((StrictJsonError, ValueError)):
        service.validate_request(b"[]")
    with pytest.raises((StrictJsonError, ValueError)):
        service.validate_request(b"null")


def test_service_validation_fails_closed_for_denied_json_and_mapping() -> None:
    denied = denied_request()
    service = M2603Service()
    with pytest.raises(M2603AuthorizationError):
        service.validate_request(denied.model_dump(mode="json"))
    with pytest.raises(M2603AuthorizationError):
        service.validate_request(denied.model_dump_json())


def test_unknown_request_fields_are_not_traversed_or_echoed() -> None:
    candidate: dict[str, object] = build_request().model_dump(mode="json")
    candidate["private_payload"] = "must-not-echo"
    with pytest.raises((M2603EvaluationError, ValidationError, ValueError)):
        M2603Service().execute(candidate)


def test_replay_rejects_nested_package_and_request_changes() -> None:
    engine = M2603Engine()
    result = engine.execute(build_request())
    assert result.reproducible_package is not None
    changed_package = result.reproducible_package.model_copy(
        update={"replay_command": "forged replay command"}
    )
    with pytest.raises(M2603ReplayError):
        engine.verify(
            result.model_copy(update={"reproducible_package": changed_package}), replay=False
        )
    changed_request = build_request().model_copy(
        update={"supersedes_result_digest": "sha256:" + "e" * 64}
    )
    with pytest.raises(M2603ReplayError):
        engine.verify(result.model_copy(update={"request": changed_request}), replay=False)


def test_workflow_definition_still_rejects_self_dependency_directly() -> None:
    request = build_request()
    step = request.workflow.steps[0]
    with pytest.raises(ValidationError):
        WorkflowDefinition(
            workflow_id="m2603.invalid",
            version="0.1.0",
            steps=(step.model_copy(update={"dependencies": (step.step_id,)}),),
            entry_step_ids=(step.step_id,),
            output_step_ids=(step.step_id,),
            workflow_digest=step.container_digest,
        )


def test_contract_closure_rejects_duplicate_steps_and_outputs() -> None:
    request = build_request()
    first, second = request.workflow.steps
    with pytest.raises(ValidationError, match="step ids must be unique"):
        WorkflowDefinition(
            workflow_id="m2603.duplicate-steps",
            version="0.1.0",
            steps=(first, first),
            entry_step_ids=(first.step_id,),
            output_step_ids=(first.step_id,),
            workflow_digest=first.container_digest,
        )
    with pytest.raises(ValidationError, match="output step ids must be unique"):
        WorkflowDefinition(
            workflow_id="m2603.duplicate-outputs",
            version="0.1.0",
            steps=(first, second),
            entry_step_ids=(first.step_id,),
            output_step_ids=(second.step_id, second.step_id),
            workflow_digest=first.container_digest,
        )
    with pytest.raises(ValidationError, match="entry and output steps must be distinct"):
        WorkflowDefinition(
            workflow_id="m2603.overlap-boundary",
            version="0.1.0",
            steps=(first, second),
            entry_step_ids=(first.step_id,),
            output_step_ids=(first.step_id,),
            workflow_digest=first.container_digest,
        )


def test_workflow_closure_rejects_cycles_unreachable_and_nonterminal_outputs() -> None:
    request = build_request()
    first, second = request.workflow.steps
    with pytest.raises(ValidationError, match="acyclic"):
        WorkflowDefinition(
            workflow_id="m2603.cycle",
            version="0.1.0",
            steps=(
                first.model_copy(update={"dependencies": (second.step_id,)}),
                second.model_copy(update={"dependencies": (first.step_id,)}),
            ),
            entry_step_ids=(first.step_id,),
            output_step_ids=(second.step_id,),
            workflow_digest=first.container_digest,
        )
    with pytest.raises(ValidationError, match="entry steps cannot depend"):
        WorkflowDefinition(
            workflow_id="m2603.entry-parent",
            version="0.1.0",
            steps=(first, second),
            entry_step_ids=(second.step_id,),
            output_step_ids=(first.step_id,),
            workflow_digest=first.container_digest,
        )
    third = first.model_copy(update={"step_id": "m2603.dead-end"})
    with pytest.raises(ValidationError, match=r"unreachable|dead-end"):
        WorkflowDefinition(
            workflow_id="m2603.unreachable",
            version="0.1.0",
            steps=(first, second, third),
            entry_step_ids=(first.step_id,),
            output_step_ids=(second.step_id,),
            workflow_digest=first.container_digest,
        )
    with pytest.raises(ValidationError, match="output steps must be terminal"):
        WorkflowDefinition(
            workflow_id="m2603.nonterminal-output",
            version="0.1.0",
            steps=(
                first,
                second,
                first.model_copy(
                    update={
                        "step_id": "m2603.trailing-step",
                        "dependencies": (second.step_id,),
                    }
                ),
            ),
            entry_step_ids=(first.step_id,),
            output_step_ids=(second.step_id,),
            workflow_digest=first.container_digest,
        )


def test_contract_closure_rejects_non_checkpointed_workflow() -> None:
    request = build_request()
    step_data = request.workflow.steps[0].model_dump(mode="python")
    false_value: Any = False
    step_data.update({"deterministic": false_value, "checkpoint_required": false_value})
    step = request.workflow.steps[0].model_construct(**step_data)
    invalid_workflow = WorkflowDefinition.model_construct(
        workflow_id="m2603.no-checkpoint",
        version="0.1.0",
        steps=(step,),
        entry_step_ids=(step.step_id,),
        output_step_ids=(step.step_id,),
        workflow_digest=step.container_digest,
    )
    with pytest.raises(ValueError, match="deterministic checkpointed"):
        cast("Any", invalid_workflow.workflow_is_closed)()


def test_attempt_and_record_closure_rejects_missing_or_unknown_attempts() -> None:
    request = build_request()
    step = request.workflow.steps[0]
    with pytest.raises(ValidationError, match="completed attempts require"):
        ExecutionAttempt(
            attempt_id="m2603.incomplete",
            step_id=step.step_id,
            retry_index=0,
            status=StepStatus.COMPLETED,
            started_at=request.context.occurred_at,
        )
    attempt = ExecutionAttempt(
        attempt_id="m2603.unknown",
        step_id="unknown-step",
        retry_index=0,
        status=StepStatus.PENDING,
        started_at=request.context.occurred_at,
    )
    with pytest.raises(ValidationError, match="unknown workflow step"):
        ExecutionRecord(
            execution_id="m2603.invalid-record",
            workflow=request.workflow,
            environment=request.environment,
            attempts=(attempt,),
            execution_status=ExecutionStatus.FAILED,
            execution_digest=step.container_digest,
        )


def test_attempt_closure_rejects_temporal_and_terminal_field_tampering() -> None:
    request = build_request()
    started = request.context.occurred_at
    with pytest.raises(ValidationError, match="finish time"):
        ExecutionAttempt(
            attempt_id="m2603.failed-without-finish",
            step_id=request.workflow.steps[0].step_id,
            retry_index=0,
            status=StepStatus.FAILED,
            started_at=started,
            failure_reason="container exited",
        )
    with pytest.raises(ValidationError, match="cannot precede"):
        ExecutionAttempt(
            attempt_id="m2603.backwards-time",
            step_id=request.workflow.steps[0].step_id,
            retry_index=0,
            status=StepStatus.COMPLETED,
            started_at=started,
            finished_at=started.replace(year=2025),
            output_digest=request.workflow.workflow_digest,
            checkpoint_digest=request.environment.environment_digest,
        )
    with pytest.raises(ValidationError, match="terminal fields"):
        ExecutionAttempt(
            attempt_id="m2603.running-with-output",
            step_id=request.workflow.steps[0].step_id,
            retry_index=0,
            status=StepStatus.RUNNING,
            started_at=started,
            output_digest=request.workflow.workflow_digest,
        )


def test_engine_preflight_and_result_closure_failure_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = M2603Engine()
    with pytest.raises(M2603AuthorizationError):
        engine.validate_request(object())
    result = engine.execute(build_request())
    with pytest.raises(M2603ReplayError):
        engine.verify(result.model_copy(update={"result_id": "forged-result-id"}), replay=False)
    with pytest.raises(M2603ReplayError):
        engine.verify(result.model_copy(update={"execution_record": None}), replay=False)
    abstained = result.model_copy(
        update={
            "status": ExecutionStatus.ABSTAINED,
            "execution_record": None,
            "reproducible_package": None,
            "abstention_reason": None,
        }
    )
    with pytest.raises(M2603ReplayError):
        engine.verify(abstained, replay=False)
    different = result.model_copy(update={"findings": ()})
    monkeypatch.setattr(engine, "execute", lambda _request: different)
    with pytest.raises(M2603ReplayError):
        engine.verify(result)
