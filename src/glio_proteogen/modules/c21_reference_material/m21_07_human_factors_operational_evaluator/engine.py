"""Deterministic caller-declared M21-07 human-factors runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m21_07 import (
    M2107_CONTRACT_VERSION,
    M2107_EVIDENCE_CLAIM,
    M2107_MODULE_ID,
    ComplexActivityHumanFactorsResult,
    EvaluateComplexActivityHumanFactorsRequest,
    EvaluationStatus,
    HumanFactorsOperationalReport,
    OperationalDimension,
    OperationalFinding,
    OperationalFindingCode,
    OperationalStatus,
    canonical_request_digest,
    result_identifier,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentState,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateComplexActivityHumanFactorsRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ComplexActivityHumanFactorsResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class M2107AuthorizationError(ValueError):
    """Caller-declared controls do not authorize operational evaluation."""

    def __init__(self) -> None:
        super().__init__(
            "M21-07 human-factors evaluation requires accepted configuration, resolved identity, "
            "granted consent, and accepted provenance/quality/support/intended-use controls"
        )


class M2107ReplayError(ValueError):
    """A human-factors result failed canonical replay verification."""


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state(candidate: object) -> object:
    value = _member(candidate, "state")
    return getattr(value, "value", value)


def preflight_m2107_authorization(candidate: object) -> None:
    """Reject denied controls before reading operational material."""

    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        expected = {
            "approved_configuration": UpstreamDecisionState.ACCEPTED.value,
            "identity_lineage": "resolved",
            "provenance": UpstreamDecisionState.ACCEPTED.value,
            "consent": ConsentState.GRANTED.value,
            "quality": UpstreamDecisionState.ACCEPTED.value,
            "support": UpstreamDecisionState.ACCEPTED.value,
            "intended_use": UpstreamDecisionState.ACCEPTED.value,
        }
        authorized = all(
            _state(_member(references, role)) == value for role, value in expected.items()
        )
    except Exception:  # noqa: BLE001 - hostile mappings fail closed.
        raise M2107AuthorizationError from None
    if not authorized:
        raise M2107AuthorizationError


def _evidence(request: EvaluateComplexActivityHumanFactorsRequest) -> tuple[EvidenceReference, ...]:
    artifacts: list[ArtifactReference] = [
        request.upstream_result,
        *request.source_artifacts,
        *(item.reference for metric in request.metrics for item in metric.evidence),
        *(item.reference for fallback in request.fallbacks for item in fallback.evidence),
        *(item.reference for item in request.configuration.evidence),
    ]
    unique: dict[str, ArtifactReference] = {}
    for artifact in artifacts:
        unique.setdefault(artifact.digest, artifact)
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M2107_EVIDENCE_CLAIM)
        for artifact in tuple(unique.values())[:64]
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=(
                f"M21-07 does not estimate {dimension} uncertainty from "
                "caller-declared operational metadata."
            ),
        )

    return UncertaintyProfile(
        measurement=unavailable("measurement"),
        sampling=unavailable("sampling"),
        parameter=unavailable("parameter"),
        model_form=unavailable("model form"),
        identification=unavailable("identification"),
        support=unavailable("support"),
        transport=unavailable("operational transport"),
        sensitivity_notes=(
            (
                "Operational targets, tolerances, sample sizes, and issuer "
                "authority are caller-declared."
            ),
            "Human-factors evidence is not a biological or treatment recommendation.",
        ),
    )


def _provenance(
    request: EvaluateComplexActivityHumanFactorsRequest, request_digest: str
) -> ProvenanceRecord:
    refs = request.context.references
    controls = (
        (ControlRole.APPROVED_CONFIGURATION, refs.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, refs.identity_lineage),
        (ControlRole.PROVENANCE, refs.provenance),
        (ControlRole.CONSENT, refs.consent),
        (ControlRole.QUALITY, refs.quality),
        (ControlRole.SUPPORT, refs.support),
        (ControlRole.INTENDED_USE, refs.intended_use),
    )
    decisions = tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=decision.decision_id,
            state=str(_state(decision)),
            policy_version=decision.policy_version,
            evidence_digest=decision.evidence.digest,
            subject_digest=getattr(decision, "binding_digest", None),
        )
        for role, decision in controls
    )
    return ProvenanceRecord(
        activity_id=f"m2107.activity.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M2107_MODULE_ID,
        module_version=M2107_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(
            dict.fromkeys(
                (
                    request_digest,
                    request.upstream_result.digest,
                    *(artifact.digest for artifact in request.source_artifacts),
                )
            )
        ),
        configuration_digest=refs.approved_configuration.evidence.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


_FINDING_CODES: Final = {
    OperationalDimension.REVIEWER_COMPREHENSION: OperationalFindingCode.COMPREHENSION_FAILURE,
    OperationalDimension.AUTOMATION_BIAS: OperationalFindingCode.AUTOMATION_BIAS_RISK,
    OperationalDimension.THROUGHPUT: OperationalFindingCode.THROUGHPUT_FAILURE,
    OperationalDimension.LATENCY: OperationalFindingCode.LATENCY_FAILURE,
    OperationalDimension.DOWNTIME: OperationalFindingCode.DOWNTIME_FAILURE,
    OperationalDimension.RECOVERY: OperationalFindingCode.RECOVERY_FAILURE,
    OperationalDimension.FALLBACK: OperationalFindingCode.FALLBACK_UNAVAILABLE,
}


def _findings(
    request: EvaluateComplexActivityHumanFactorsRequest,
    evidence: tuple[EvidenceReference, ...],
) -> tuple[OperationalFinding, ...]:
    findings: list[OperationalFinding] = []
    for metric in request.metrics:
        if metric.status is not OperationalStatus.FAIL:
            continue
        code = _FINDING_CODES[metric.dimension]
        findings.append(
            OperationalFinding(
                finding_id=f"finding.m2107.{code.value}",
                code=code,
                message=f"Caller-declared {metric.dimension.value} operational target failed.",
                evidence=evidence[:1],
            )
        )
    if any(item.status is OperationalStatus.FAIL for item in request.fallbacks):
        findings.append(
            OperationalFinding(
                finding_id="finding.m2107.fallback_unavailable",
                code=OperationalFindingCode.FALLBACK_UNAVAILABLE,
                message="Caller-declared fallback scenario requires operational review.",
                evidence=evidence[:1],
            )
        )
    if not findings:
        findings.append(
            OperationalFinding(
                finding_id="finding.m2107.provisional_review",
                code=OperationalFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                message="The provisional ABI requires governed owner review.",
                evidence=evidence[:1],
            )
        )
    return tuple(findings)


def _report(
    request: EvaluateComplexActivityHumanFactorsRequest,
    request_digest: str,
    evidence: tuple[EvidenceReference, ...],
) -> HumanFactorsOperationalReport:
    return HumanFactorsOperationalReport(
        report_id=f"report.m2107.{request_digest.removeprefix('sha256:')}",
        version=request.configuration.version,
        metrics=request.metrics,
        fallbacks=request.fallbacks,
        configuration=request.configuration,
        evidence=evidence,
    )


def _limitations(*, abstained: bool) -> tuple[Limitation, ...]:
    limitations = [
        Limitation(
            code="caller_declared_operational_material",
            statement=(
                "Operational metrics, targets, tolerances, fallback paths, and "
                "issuer authority are caller-declared."
            ),
        ),
        Limitation(
            code="prohibited_outputs",
            statement=(
                "No complex-activity estimate, kinase activity, all-omics fusion, "
                "treatment recommendation, identity inference, or consent inference "
                "is emitted."
            ),
        ),
    ]
    if abstained:
        limitations.append(
            Limitation(
                code="safe_abstention",
                statement="Non-evaluable operational material produces no human-factors report.",
            )
        )
    return tuple(limitations)


class M2107Engine:
    """Evaluate caller-declared human-factors and operational material."""

    __slots__ = ()

    def evaluate(self, request: object) -> ComplexActivityHumanFactorsResult:
        preflight_m2107_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        return self._result(validated)

    def _result(
        self, request: EvaluateComplexActivityHumanFactorsRequest
    ) -> ComplexActivityHumanFactorsResult:
        request_digest = canonical_request_digest(request)
        evidence = _evidence(request)
        abstained = any(
            item.status is OperationalStatus.NOT_EVALUABLE for item in request.metrics
        ) or any(item.status is OperationalStatus.NOT_EVALUABLE for item in request.fallbacks)
        report = None if abstained else _report(request, request_digest, evidence)
        findings = (
            (
                OperationalFinding(
                    finding_id="finding.m2107.evaluation_incomplete",
                    code=OperationalFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                    message="One or more operational dimensions are not evaluable.",
                    evidence=evidence[:1],
                ),
            )
            if abstained
            else _findings(request, evidence)
        )
        payload: dict[str, Any] = {
            "output_type": "complex_activity_human_factors",
            "result_id": result_identifier(request),
            "result_version": M2107_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": EvaluationStatus.ABSTAINED if abstained else EvaluationStatus.EVALUATED,
            "report": report,
            "findings": findings,
            "abstention_reason": (
                "Human-factors operational dimensions are not safely evaluable."
                if abstained
                else None
            ),
            "parent_target": "complex activity",
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED if abstained else SupportStatus.SUPPORTED,
                reason_code="m2107_operational_abstained"
                if abstained
                else "m2107_operational_evaluated",
                rationale=(
                    "At least one operational dimension is not evaluable; review is required."
                    if abstained
                    else "All configured operational dimensions are represented."
                ),
            ),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(request, request_digest),
            "evidence": evidence,
            "limitations": _limitations(abstained=abstained),
            "human_review_required": True,
        }
        provisional = ComplexActivityHumanFactorsResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(provisional)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def replay(
        self, result: ComplexActivityHumanFactorsResult
    ) -> ComplexActivityHumanFactorsResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M2107ReplayError from error
        if validated.request_digest != canonical_request_digest(validated.request):
            raise M2107ReplayError
        if validated.result_id != result_identifier(validated.request):
            raise M2107ReplayError
        if validated.result_digest != result_payload_digest(validated):
            raise M2107ReplayError
        expected = self.evaluate(validated.request)
        if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
            raise M2107ReplayError
        return validated


def evaluate_complex_activity_human_factors(
    request: object,
) -> ComplexActivityHumanFactorsResult:
    """Public stateless M21-07 operational evaluation entry point."""

    return M2107Engine().evaluate(request)


__all__ = [
    "M2107AuthorizationError",
    "M2107Engine",
    "M2107ReplayError",
    "evaluate_complex_activity_human_factors",
    "preflight_m2107_authorization",
]
