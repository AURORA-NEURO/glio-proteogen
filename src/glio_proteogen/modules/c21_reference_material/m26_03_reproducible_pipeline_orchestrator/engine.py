"""Deterministic caller-declared M26-03 pipeline execution runtime."""

# Exception text is intentionally sanitized at the service/API boundaries.
# ruff: noqa: TRY003

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m26_03 import (
    M2603_CONTRACT_VERSION,
    M2603_EVIDENCE_CLAIM,
    M2603_MODULE_ID,
    ExecuteProteinSubtypeWorkflowRequest,
    ExecutionAttempt,
    ExecutionRecord,
    ExecutionStatus,
    PipelineFinding,
    PipelineFindingCode,
    ProteinSubtypeExecutionResult,
    ReproducibleResultPackage,
    StepStatus,
    WorkflowDefinition,
    WorkflowStep,
    canonical_request_digest,
    result_identifier,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentState,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)

_REQUEST_ADAPTER: Final = TypeAdapter(ExecuteProteinSubtypeWorkflowRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinSubtypeExecutionResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_EXPECTED_CONTROLS: Final = {
    "approved_configuration": UpstreamDecisionState.ACCEPTED.value,
    "identity_lineage": IdentityLineageState.RESOLVED.value,
    "provenance": UpstreamDecisionState.ACCEPTED.value,
    "consent": ConsentState.GRANTED.value,
    "quality": UpstreamDecisionState.ACCEPTED.value,
    "support": UpstreamDecisionState.ACCEPTED.value,
    "intended_use": UpstreamDecisionState.ACCEPTED.value,
}


class M2603AuthorizationError(ValueError):
    """Caller-declared controls do not authorize execution."""


class M2603EvaluationError(ValueError):
    """A pipeline request failed safe validation or construction."""


class M2603ReplayError(ValueError):
    """A pipeline result failed canonical replay verification."""


def _member(candidate: object, name: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(name)
    return getattr(candidate, name, None)


def _state(candidate: object) -> str | None:
    value = _member(candidate, "state")
    actual = getattr(value, "value", value)
    return actual if isinstance(actual, str) else None


def preflight_m2603_authorization(candidate: object) -> None:
    """Reject denied controls before traversing workflow declarations."""

    try:
        references = _member(_member(candidate, "context"), "references")
        authorized = all(
            _state(_member(references, role)) == expected
            for role, expected in _EXPECTED_CONTROLS.items()
        )
    except Exception as error:
        raise M2603AuthorizationError("M26-03 controls are malformed") from error
    if not authorized:
        raise M2603AuthorizationError("M26-03 requires all seven accepted controls")


def _evidence(request: ExecuteProteinSubtypeWorkflowRequest) -> tuple[EvidenceReference, ...]:
    artifacts: list[ArtifactReference] = [*request.source_artifacts]
    artifacts.extend(item.reference for item in request.workflow.evidence)
    artifacts.extend(item.reference for item in request.environment.evidence)
    unique: dict[str, ArtifactReference] = {item.digest: item for item in artifacts}
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M2603_EVIDENCE_CLAIM)
        for artifact in unique.values()
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=(
                f"M26-03 does not estimate {dimension} uncertainty from orchestration metadata."
            ),
        )

    return UncertaintyProfile(
        measurement=unavailable("measurement"),
        sampling=unavailable("sampling"),
        parameter=unavailable("parameter"),
        model_form=unavailable("model form"),
        identification=unavailable("identification"),
        support=unavailable("support"),
        transport=unavailable("transport"),
        sensitivity_notes=(
            "Execution evidence is caller-declared and does not establish biological "
            "or clinical uncertainty.",
        ),
    )


def _provenance(
    request: ExecuteProteinSubtypeWorkflowRequest, request_digest: str
) -> ProvenanceRecord:
    references = request.context.references
    controls = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, references.identity_lineage),
        (ControlRole.PROVENANCE, references.provenance),
        (ControlRole.CONSENT, references.consent),
        (ControlRole.QUALITY, references.quality),
        (ControlRole.SUPPORT, references.support),
        (ControlRole.INTENDED_USE, references.intended_use),
    )
    decisions = tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=decision.decision_id,
            state=str(_state(decision)),
            policy_version=decision.policy_version,
            evidence_digest=decision.evidence.digest,
            subject_digest=(
                decision.binding_digest if hasattr(decision, "binding_digest") else None
            ),
        )
        for role, decision in controls
    )
    return ProvenanceRecord(
        activity_id="m2603.activity." + request_digest.removeprefix("sha256:"),
        actor_id=request.context.actor_id,
        module_id=M2603_MODULE_ID,
        module_version=M2603_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(item.digest for item in request.source_artifacts),
        configuration_digest=sha256_digest(
            {"workflow": request.workflow, "environment": request.environment}
        ),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=decisions,
    )


def _topological_steps(workflow: WorkflowDefinition) -> tuple[WorkflowStep, ...]:
    """Return a stable dependency-respecting order for caller-declared steps."""

    pending = {step.step_id: step for step in workflow.steps}
    completed: set[str] = set()
    ordered: list[WorkflowStep] = []
    while pending:
        ready = tuple(
            sorted(
                (step for step in pending.values() if set(step.dependencies) <= completed),
                key=lambda step: step.step_id,
            )
        )
        if not ready:
            raise M2603EvaluationError("M26-03 workflow graph cannot be scheduled")
        ordered.extend(ready)
        for step in ready:
            completed.add(step.step_id)
            del pending[step.step_id]
    return tuple(ordered)


def _attempts(request: ExecuteProteinSubtypeWorkflowRequest) -> tuple[ExecutionAttempt, ...]:
    return tuple(
        ExecutionAttempt(
            attempt_id="attempt." + step.step_id,
            step_id=step.step_id,
            retry_index=0,
            status=StepStatus.COMPLETED,
            started_at=request.context.occurred_at,
            finished_at=request.context.occurred_at,
            output_digest=sha256_digest(
                {"step": step.step_id, "version": step.version, "request": request.request_id}
            ),
            checkpoint_digest=sha256_digest(
                {"checkpoint": step.step_id, "container": step.container_digest}
            ),
            evidence=step.evidence,
        )
        for step in _topological_steps(request.workflow)
    )


def _execution_record(
    request: ExecuteProteinSubtypeWorkflowRequest,
    attempts: tuple[ExecutionAttempt, ...],
) -> ExecutionRecord:
    execution_digest = sha256_digest(
        {"workflow": request.workflow, "environment": request.environment, "attempts": attempts}
    )
    return ExecutionRecord(
        execution_id="execution." + execution_digest.removeprefix("sha256:"),
        workflow=request.workflow,
        environment=request.environment,
        attempts=attempts,
        execution_status=ExecutionStatus.COMPLETED,
        execution_digest=execution_digest,
        evidence=_evidence(request),
    )


def _package(
    request: ExecuteProteinSubtypeWorkflowRequest,
    record: ExecutionRecord,
) -> ReproducibleResultPackage:
    result_artifact = ArtifactReference(
        artifact_id="m2603-result." + record.execution_id.removeprefix("execution."),
        version=M2603_CONTRACT_VERSION,
        digest=record.execution_digest,
        media_type="application/vnd.glio-proteogen.m26-03+json",
    )
    return ReproducibleResultPackage(
        package_id="package." + record.execution_digest.removeprefix("sha256:"),
        version=request.workflow.version,
        execution_id=record.execution_id,
        result_artifact=result_artifact,
        manifest_artifacts=request.source_artifacts,
        replay_command=(
            "glio-proteogen-m26-03 replay --request <canonical-request.json> "
            "--environment <locked-environment.json>"
        ),
        package_digest=sha256_digest(
            {
                "execution_id": record.execution_id,
                "result": result_artifact,
                "manifest": request.source_artifacts,
            }
        ),
        evidence=_evidence(request),
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="caller_declared_execution",
            statement="Workflow, containers, environment, and artifacts are caller-declared.",
        ),
        Limitation(
            code="research_only_orchestration",
            statement=(
                "The orchestrator makes no biological, treatment, identity, or consent claim."
            ),
        ),
        Limitation(
            code="human_review_required",
            statement=(
                "Human review remains required for provisional ABI confirmation and exceptions."
            ),
        ),
    )


class M2603Engine:
    """Stateless deterministic execution and replay engine."""

    def validate_request(self, candidate: object) -> ExecuteProteinSubtypeWorkflowRequest:
        preflight_m2603_authorization(candidate)
        try:
            return _REQUEST_ADAPTER.validate_python(candidate, strict=True)
        except Exception as error:
            raise M2603EvaluationError("M26-03 request is invalid") from error

    def execute(self, candidate: object) -> ProteinSubtypeExecutionResult:
        request = self.validate_request(candidate)
        request_digest = canonical_request_digest(request)
        attempts = _attempts(request)
        record = _execution_record(request, attempts)
        package = _package(request, record)
        evidence = _evidence(request)
        payload: dict[str, Any] = {
            "output_type": "protein_subtype_execution",
            "result_id": result_identifier(request),
            "result_version": M2603_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": ExecutionStatus.COMPLETED,
            "execution_record": record,
            "reproducible_package": package,
            "findings": (
                PipelineFinding(
                    finding_id="finding.m2603.provisional-review",
                    code=PipelineFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                    message=(
                        "The provisional workflow ABI and caller authority require governed review."
                    ),
                    evidence=evidence[:1],
                ),
            ),
            "abstention_reason": None,
            "parent_target": "protein subtype",
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="m2603_execution_completed",
                rationale=(
                    "Every declared deterministic step completed with a checkpoint and "
                    "locked environment."
                ),
            ),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(request, request_digest),
            "evidence": evidence,
            "limitations": _limitations(),
            "human_review_required": True,
        }
        constructed = ProteinSubtypeExecutionResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(constructed)
        try:
            return _RESULT_ADAPTER.validate_python(payload, strict=True)
        except Exception as error:
            raise M2603EvaluationError("M26-03 result construction failed safely") from error

    def verify(self, result: object, *, replay: bool = True) -> ProteinSubtypeExecutionResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M2603ReplayError("M26-03 result is invalid") from error
        if validated.result_digest != result_payload_digest(validated):
            raise M2603ReplayError("M26-03 result digest mismatch")
        if replay:
            expected = self.execute(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M2603ReplayError("M26-03 deterministic replay mismatch")
        return validated


def execute_protein_subtype_workflow(candidate: object) -> ProteinSubtypeExecutionResult:
    """Public stateless M26-03 execution entry point."""

    return M2603Engine().execute(candidate)


__all__ = [
    "M2603AuthorizationError",
    "M2603Engine",
    "M2603EvaluationError",
    "M2603ReplayError",
    "execute_protein_subtype_workflow",
    "preflight_m2603_authorization",
]
