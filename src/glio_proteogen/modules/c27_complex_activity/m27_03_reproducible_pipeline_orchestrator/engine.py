"""Deterministic caller-declared runtime for provisional M27-03."""

# Boundary errors are intentionally sanitized by service/API adapters.
# ruff: noqa: TRY003,E501,S101,C420

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, cast

from pydantic import BaseModel, TypeAdapter

from glio_proteogen.contracts.m27_03 import (
    M2703_CONTRACT_VERSION,
    M2703_MAX_CANONICAL_REQUEST_BYTES,
    M2703_MODULE_ID,
    ComplexActivityPipelineResult,
    ExecutionRecord,
    ExecutionStatus,
    FindingCode,
    OrchestrateComplexActivityPipelineRequest,
    PipelineFinding,
    PipelineStatus,
    ReproducibleResultPackage,
    SafeFailureReport,
)
from glio_proteogen.contracts.m27_03.canonical import (
    canonical_request_digest,
    execution_id_for_request_digest,
    package_id_for_request_digest,
    result_id_for_request_digest,
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

_REQUEST_ADAPTER: Final = TypeAdapter(OrchestrateComplexActivityPipelineRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ComplexActivityPipelineResult)
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
_MAX_PLAIN_DEPTH: Final = 64
_MAX_PLAIN_DICT_ITEMS: Final = 512
_MAX_PLAIN_SEQUENCE_ITEMS: Final = 512
_MAX_PLAIN_NODES: Final = 250_000


class M2703AuthorizationError(ValueError):
    """Caller-declared controls do not authorize execution."""


class M2703EvaluationError(ValueError):
    """A request cannot be evaluated safely."""


class M2703ReplayError(ValueError):
    """A result failed canonical replay verification."""


def _member(candidate: object, name: str) -> object:
    if isinstance(candidate, Mapping):
        candidate_mro = type.__getattribute__(type(candidate), "__mro__")
        if dict in candidate_mro:
            return dict.get(cast("dict[object, object]", candidate), name)
        return candidate.get(name)
    return getattr(candidate, name, None)


def _state(candidate: object) -> str | None:
    value = _member(candidate, "state")
    actual = getattr(value, "value", value)
    return actual if isinstance(actual, str) else None


def preflight_m2703_authorization(candidate: object) -> None:
    """Require all seven caller-declared controls before orchestration."""

    references = _member(_member(candidate, "context"), "references")
    if references is None:
        raise M2703AuthorizationError("M27-03 controls are malformed")
    try:
        authorized = all(
            _state(_member(references, role)) == expected
            for role, expected in _EXPECTED_CONTROLS.items()
        )
    except Exception as error:
        raise M2703AuthorizationError("M27-03 controls are malformed") from error
    if not authorized:
        raise M2703AuthorizationError("M27-03 requires all seven accepted controls")


class _InvalidPlainValueError(TypeError):
    def __init__(self) -> None:
        super().__init__("M27-03 values require bounded built-in containers")


def _charge_plain_bytes(budget: list[int], value: str) -> None:
    budget[0] -= len(value.encode("utf-8")) + 2
    if budget[0] < 0:
        raise _InvalidPlainValueError


def _plain_value(  # noqa: C901, PLR0912 - exact built-in traversal firewall.
    candidate: object,
    *,
    max_bytes: int = M2703_MAX_CANONICAL_REQUEST_BYTES,
    _depth: int = 0,
    _budget: list[int] | None = None,
    _byte_budget: list[int] | None = None,
) -> object:
    """Materialize only bounded built-in containers for direct replay ingress."""

    if _depth > _MAX_PLAIN_DEPTH:
        raise _InvalidPlainValueError
    budget = [_MAX_PLAIN_NODES] if _budget is None else _budget
    byte_budget = [max_bytes] if _byte_budget is None else _byte_budget
    budget[0] -= 1
    if budget[0] < 0:
        raise _InvalidPlainValueError
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if BaseModel in candidate_mro:
        return candidate
    if dict in candidate_mro:
        mapping = cast("dict[object, object]", candidate)
        if dict.__len__(mapping) > _MAX_PLAIN_DICT_ITEMS:
            raise _InvalidPlainValueError
        result: dict[str, object] = {}
        for key in dict.keys(mapping):
            if type(key) is not str:
                raise _InvalidPlainValueError
            _charge_plain_bytes(byte_budget, key)
            result[key] = _plain_value(
                dict.__getitem__(mapping, key),
                _depth=_depth + 1,
                _budget=budget,
                _byte_budget=byte_budget,
            )
        return result
    if list in candidate_mro:
        list_values = cast("list[object]", candidate)
        if list.__len__(list_values) > _MAX_PLAIN_SEQUENCE_ITEMS:
            raise _InvalidPlainValueError
        return [
            _plain_value(
                item,
                _depth=_depth + 1,
                _budget=budget,
                _byte_budget=byte_budget,
            )
            for item in list.__iter__(list_values)
        ]
    if tuple in candidate_mro:
        tuple_values = cast("tuple[object, ...]", candidate)
        if tuple.__len__(tuple_values) > _MAX_PLAIN_SEQUENCE_ITEMS:
            raise _InvalidPlainValueError
        return tuple(
            _plain_value(
                item,
                _depth=_depth + 1,
                _budget=budget,
                _byte_budget=byte_budget,
            )
            for item in tuple.__iter__(tuple_values)
        )
    if Mapping in candidate_mro or isinstance(candidate, Mapping):
        raise _InvalidPlainValueError
    if type(candidate) is str:
        _charge_plain_bytes(byte_budget, candidate)
    return candidate


def _evidence(request: OrchestrateComplexActivityPipelineRequest) -> tuple[EvidenceReference, ...]:
    artifacts: list[ArtifactReference] = [request.upstream_result, *request.source_artifacts]
    artifacts.extend(item.reference for item in request.workflow.evidence)
    artifacts.extend(item.reference for node in request.workflow.nodes for item in node.evidence)
    artifacts.extend(item.reference for edge in request.workflow.edges for item in edge.evidence)
    artifacts.extend(item.reference for item in request.policy.evidence)
    unique = {artifact.digest: artifact for artifact in artifacts}
    return tuple(
        EvidenceReference(
            reference=artifact, role="evidence", claim="caller-declared pipeline evidence"
        )
        for artifact in unique.values()
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=f"M27-03 does not estimate {dimension} uncertainty from orchestration metadata.",
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
            "Execution provenance does not establish complex-activity biology or clinical utility.",
        ),
    )


def _provenance(
    request: OrchestrateComplexActivityPipelineRequest, request_digest: str
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
        activity_id="m2703.activity." + request_digest.removeprefix("sha256:"),
        actor_id=request.context.actor_id,
        module_id=M2703_MODULE_ID,
        module_version=M2703_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request.upstream_result.digest,
            *(item.digest for item in request.source_artifacts),
        ),
        configuration_digest=sha256_digest(
            {"workflow": request.workflow, "policy": request.policy}
        ),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=decisions,
    )


def _topological_nodes(request: OrchestrateComplexActivityPipelineRequest) -> tuple[str, ...]:
    nodes = {node.node_id: node for node in request.workflow.nodes}
    outgoing: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    indegree = {node_id: 0 for node_id in nodes}
    for edge in request.workflow.edges:
        outgoing[edge.source_node_id].append(edge.target_node_id)
        indegree[edge.target_node_id] += 1
    ready = sorted(node_id for node_id, count in indegree.items() if count == 0)
    ordered: list[str] = []
    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for target in sorted(outgoing[current]):
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
                ready.sort()
    if len(ordered) != len(nodes):
        raise M2703EvaluationError("M27-03 workflow graph cannot be scheduled")
    return tuple(ordered)


def _execution(
    request: OrchestrateComplexActivityPipelineRequest,
    request_digest: str,
) -> ExecutionRecord:
    order = _topological_nodes(request)
    environment_digest = sha256_digest(
        {
            "workflow": request.workflow,
            "policy": request.policy,
            "containers": tuple(
                (node.node_id, node.container_image, node.container_digest, node.version)
                for node in request.workflow.nodes
            ),
        }
    )
    output_digest = sha256_digest(
        {
            "request": request_digest,
            "seed": request.policy.deterministic_seed,
            "order": order,
            "upstream": request.upstream_result.digest,
        }
    )
    checkpoint_digest = sha256_digest(
        {
            "interval": request.policy.checkpoint_interval_nodes,
            "completed": order[:: request.policy.checkpoint_interval_nodes],
            "environment": environment_digest,
        }
    )
    return ExecutionRecord(
        execution_id=execution_id_for_request_digest(request_digest),
        workflow_id=request.workflow.workflow_id,
        policy=request.policy,
        status=ExecutionStatus.SUCCEEDED,
        attempts=1,
        completed_node_ids=order,
        checkpoint_digest=checkpoint_digest,
        environment_digest=environment_digest,
        output_digest=output_digest,
        evidence=_evidence(request),
    )


def _package(
    request: OrchestrateComplexActivityPipelineRequest,
    request_digest: str,
    execution: ExecutionRecord,
) -> ReproducibleResultPackage:
    assert execution.output_digest is not None
    artifact = ArtifactReference(
        artifact_id="m2703.result." + request_digest.removeprefix("sha256:"),
        version=M2703_CONTRACT_VERSION,
        digest=execution.output_digest,
        media_type="application/vnd.glio-proteogen.m27-03+json",
    )
    manifest_digest = sha256_digest(
        {
            "upstream": request.upstream_result,
            "sources": request.source_artifacts,
            "workflow": request.workflow,
        }
    )
    reproducibility_digest = sha256_digest(
        {
            "manifest": manifest_digest,
            "environment": execution.environment_digest,
            "output": execution.output_digest,
        }
    )
    return ReproducibleResultPackage(
        package_id=package_id_for_request_digest(request_digest),
        version=M2703_CONTRACT_VERSION,
        execution_id=execution.execution_id,
        # Retain the M27-02 lineage artifact as a first-class package member.
        # It is already bound by the manifest and evidence projection, but
        # omitting it here made a stored package incomplete for consumers that
        # inspect only artifact_references when reconstructing inputs.
        artifact_references=(artifact, request.upstream_result, *request.source_artifacts),
        manifest_digest=manifest_digest,
        environment_digest=execution.environment_digest,
        reproducibility_digest=reproducibility_digest,
        evidence=_evidence(request),
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="caller_declared_execution",
            statement="Workflow, containers, environment, and artifacts are caller-declared.",
        ),
        Limitation(
            code="no_biological_inference",
            statement="The orchestrator emits no protein, proteoform, isoform, or complex-activity biological inference.",
        ),
        Limitation(
            code="provisional_abi",
            statement="The M27-02 input and M27-03 output ABI remain provisional pending owner confirmation.",
        ),
    )


class M2703Engine:
    """Stateless deterministic orchestration, safe failure, and replay engine."""

    def validate_request(self, candidate: object) -> OrchestrateComplexActivityPipelineRequest:
        try:
            return _REQUEST_ADAPTER.validate_python(_plain_value(candidate), strict=True)
        except Exception as error:
            raise M2703EvaluationError("M27-03 request is invalid") from error

    def _abstain(
        self,
        request: OrchestrateComplexActivityPipelineRequest,
        request_digest: str,
        trigger: str,
        code: FindingCode,
    ) -> ComplexActivityPipelineResult:
        evidence = _evidence(request)
        safe_failure = SafeFailureReport(
            report_id="m2703.safe-failure." + request_digest.removeprefix("sha256:"),
            version=M2703_CONTRACT_VERSION,
            trigger=trigger,
            action="abstain without executing nodes or emitting a reproducible result package",
            recovery_note="Resolve the caller-declared control or ABI condition and resubmit for review.",
            evidence=evidence,
        )
        payload: dict[str, Any] = {
            "output_type": "complex_activity_pipeline",
            "result_id": result_id_for_request_digest(request_digest),
            "result_version": M2703_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": PipelineStatus.ABSTAINED,
            "execution_record": None,
            "result_package": None,
            "findings": (
                PipelineFinding(
                    finding_id="m2703.finding.abstention",
                    code=code,
                    message=trigger,
                    evidence=evidence[:1],
                ),
            ),
            "safe_failure_report": safe_failure,
            "abstention_reason": trigger,
            "support_decision": SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="m2703_safe_abstention",
                rationale="Pipeline execution is not supported under the caller-declared controls or provisional ABI.",
            ),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(request, request_digest),
            "evidence": evidence,
            "limitations": _limitations(),
            "human_review_required": True,
        }
        constructed = ComplexActivityPipelineResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def execute(self, candidate: object) -> ComplexActivityPipelineResult:
        request = self.validate_request(candidate)
        request_digest = canonical_request_digest(request)
        try:
            preflight_m2703_authorization(request)
        except M2703AuthorizationError as error:
            return self._abstain(
                request, request_digest, str(error), FindingCode.UPSTREAM_UNSUPPORTED
            )
        try:
            execution = _execution(request, request_digest)
            package = _package(request, request_digest, execution)
        except (M2703EvaluationError, ValueError) as error:
            return self._abstain(request, request_digest, str(error), FindingCode.NODE_FAILED)
        evidence = _evidence(request)
        payload: dict[str, Any] = {
            "output_type": "complex_activity_pipeline",
            "result_id": result_id_for_request_digest(request_digest),
            "result_version": M2703_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": PipelineStatus.EXECUTED,
            "execution_record": execution,
            "result_package": package,
            "findings": (
                PipelineFinding(
                    finding_id="m2703.finding.provisional",
                    code=FindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                    message="M27-03 remains a provisional caller-declared orchestration ABI.",
                    evidence=evidence[:1],
                ),
            ),
            "safe_failure_report": None,
            "abstention_reason": None,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="m2703_execution_completed",
                rationale="Every declared deterministic node completed with environment and checkpoint evidence.",
            ),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(request, request_digest),
            "evidence": evidence,
            "limitations": _limitations(),
            "human_review_required": False,
        }
        constructed = ComplexActivityPipelineResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(constructed)
        try:
            return _RESULT_ADAPTER.validate_python(payload, strict=True)
        except Exception as error:
            raise M2703EvaluationError("M27-03 result construction failed safely") from error

    def verify(self, result: object, *, replay: bool = True) -> ComplexActivityPipelineResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M2703ReplayError("M27-03 result is invalid") from error
        if validated.result_digest != result_payload_digest(validated):
            raise M2703ReplayError("M27-03 result digest mismatch")
        if replay and self.execute(validated.request).model_dump(
            mode="json"
        ) != validated.model_dump(mode="json"):
            raise M2703ReplayError("M27-03 deterministic replay mismatch")
        return validated


def execute_complex_activity_pipeline(candidate: object) -> ComplexActivityPipelineResult:
    """Public stateless execution entry point."""

    return M2703Engine().execute(candidate)


__all__ = [
    "M2703AuthorizationError",
    "M2703Engine",
    "M2703EvaluationError",
    "M2703ReplayError",
    "execute_complex_activity_pipeline",
    "preflight_m2703_authorization",
]
