"""Deterministic, caller-declared M21-05 subgroup equity evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m21_05 import (
    M2105_CONTRACT_VERSION,
    M2105_EVIDENCE_CLAIM,
    M2105_MODULE_ID,
    ComplexActivitySubgroupEvaluationResult,
    CoverageStatus,
    EquityStatus,
    EvaluateComplexActivitySubgroupEquityRequest,
    EvaluationStatus,
    SubgroupEvaluationReport,
    SubgroupFinding,
    SubgroupFindingCode,
    canonical_request_digest,
    result_payload_digest,
)
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

# ruff: noqa: TRY003

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateComplexActivitySubgroupEquityRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ComplexActivitySubgroupEvaluationResult)
_ZERO_DIGEST: Final = "sha256:" + "0" * 64
_EXPECTED_CONTROLS: Final = {
    "approved_configuration": UpstreamDecisionState.ACCEPTED.value,
    "identity_lineage": IdentityLineageState.RESOLVED.value,
    "provenance": UpstreamDecisionState.ACCEPTED.value,
    "consent": ConsentState.GRANTED.value,
    "quality": UpstreamDecisionState.ACCEPTED.value,
    "support": UpstreamDecisionState.ACCEPTED.value,
    "intended_use": UpstreamDecisionState.ACCEPTED.value,
}


class M2105AuthorizationError(ValueError):
    """Raised when caller-declared controls do not authorize evaluation."""


class M2105EvaluationError(ValueError):
    """Raised when a request cannot be evaluated safely."""


class M2105ReplayError(ValueError):
    """Raised when a result digest or deterministic replay is invalid."""


def _member(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _state(value: object) -> str | None:
    candidate = _member(value, "state")
    if isinstance(candidate, str):
        return candidate
    state_value = getattr(candidate, "value", None)
    return state_value if isinstance(state_value, str) else None


def preflight_m2105_authorization(candidate: object) -> None:
    """Fail closed before subgroup metric traversal."""

    try:
        references = _member(_member(candidate, "context"), "references")
    except Exception as error:
        raise M2105AuthorizationError from error
    if references is None:
        raise M2105AuthorizationError("M21-05 requires all seven upstream controls")
    for role, expected in _EXPECTED_CONTROLS.items():
        decision = _member(references, role)
        actual = _state(decision)
        if actual != expected:
            raise M2105AuthorizationError(
                f"M21-05 control {role} must be {expected}; received {actual}"
            )


def _evidence(
    request: EvaluateComplexActivitySubgroupEquityRequest,
) -> tuple[EvidenceReference, ...]:
    artifacts: list[ArtifactReference] = [request.upstream_result, *request.source_artifacts]
    artifacts.append(request.configuration.evidence[0].reference)
    artifacts.extend(evidence_item.reference for evidence_item in request.configuration.evidence)
    artifacts.extend(
        evidence_item.reference
        for performance_item in request.performance
        for evidence_item in performance_item.evidence
    )
    artifacts.extend(
        evidence_item.reference
        for calibration_item in request.calibration
        for evidence_item in calibration_item.evidence
    )
    artifacts.extend(
        evidence_item.reference
        for coverage_item in request.coverage
        for evidence_item in coverage_item.evidence
    )
    refs = request.context.references
    artifacts.extend(
        (
            refs.approved_configuration.evidence,
            refs.identity_lineage.evidence,
            refs.provenance.evidence,
            refs.consent.evidence,
            refs.quality.evidence,
            refs.support.evidence,
            refs.intended_use.evidence,
        )
    )
    unique = {item.digest: item for item in artifacts}
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M2105_EVIDENCE_CLAIM)
        for artifact in unique.values()
    )


def _uncertainty(*, evaluated: bool) -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED if evaluated else EstimateState.NOT_ESTIMABLE,
        probability=0.9 if evaluated else None,
        rationale=(
            (
                "Caller-declared subgroup performance, calibration and coverage "
                "satisfy the locked evaluation policy."
            )
            if evaluated
            else "The subgroup equity request is outside the safe evaluation envelope."
        ),
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=(
            (
                "Evaluation is sensitive to subgroup support, safety floors, coverage "
                "and calibration targets."
            ),
        ),
    )


def _provenance(
    request: EvaluateComplexActivitySubgroupEquityRequest,
    request_digest: str,
) -> ProvenanceRecord:
    refs = request.context.references
    controls = (
        ControlDecisionRecord(
            role=ControlRole.APPROVED_CONFIGURATION,
            decision_id=refs.approved_configuration.decision_id,
            state=refs.approved_configuration.state.value,
            policy_version=refs.approved_configuration.policy_version,
            evidence_digest=refs.approved_configuration.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.IDENTITY_LINEAGE,
            decision_id=refs.identity_lineage.decision_id,
            state=refs.identity_lineage.state.value,
            policy_version=refs.identity_lineage.policy_version,
            evidence_digest=refs.identity_lineage.evidence.digest,
            subject_digest=refs.identity_lineage.binding_digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.PROVENANCE,
            decision_id=refs.provenance.decision_id,
            state=refs.provenance.state.value,
            policy_version=refs.provenance.policy_version,
            evidence_digest=refs.provenance.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.CONSENT,
            decision_id=refs.consent.decision_id,
            state=refs.consent.state.value,
            policy_version=refs.consent.policy_version,
            evidence_digest=refs.consent.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.QUALITY,
            decision_id=refs.quality.decision_id,
            state=refs.quality.state.value,
            policy_version=refs.quality.policy_version,
            evidence_digest=refs.quality.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.SUPPORT,
            decision_id=refs.support.decision_id,
            state=refs.support.state.value,
            policy_version=refs.support.policy_version,
            evidence_digest=refs.support.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.INTENDED_USE,
            decision_id=refs.intended_use.decision_id,
            state=refs.intended_use.state.value,
            policy_version=refs.intended_use.policy_version,
            evidence_digest=refs.intended_use.evidence.digest,
        ),
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M2105_MODULE_ID,
        module_version=M2105_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request_digest,
            request.upstream_result.digest,
            *(artifact.digest for artifact in request.source_artifacts),
        ),
        configuration_digest=request.configuration.evidence[0].reference.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=controls,
    )


def _finding(
    finding_id: str,
    code: SubgroupFindingCode,
    message: str,
    evidence: tuple[EvidenceReference, ...],
) -> SubgroupFinding:
    return SubgroupFinding(finding_id=finding_id, code=code, message=message, evidence=evidence[:1])


def _findings(
    request: EvaluateComplexActivitySubgroupEquityRequest,
    evidence: tuple[EvidenceReference, ...],
) -> tuple[SubgroupFinding, ...]:
    findings: list[SubgroupFinding] = []
    for performance_item in request.performance:
        if performance_item.coverage_status is CoverageStatus.UNSUPPORTED:
            findings.append(
                _finding(
                    f"finding.{performance_item.metric_id}.unsupported",
                    SubgroupFindingCode.UPSTREAM_UNSUPPORTED,
                    "Unsupported subgroup evidence cannot be promoted.",
                    evidence,
                )
            )
        elif performance_item.coverage_status is CoverageStatus.NOT_EVALUABLE:
            findings.append(
                _finding(
                    f"finding.{performance_item.metric_id}.coverage",
                    SubgroupFindingCode.COVERAGE_LIMITED,
                    "Subgroup coverage is not evaluable.",
                    evidence,
                )
            )
        elif performance_item.coverage_status is CoverageStatus.LIMITED:
            findings.append(
                _finding(
                    f"finding.{performance_item.metric_id}.limited",
                    SubgroupFindingCode.COVERAGE_LIMITED,
                    "Subgroup coverage is limited and requires review.",
                    evidence,
                )
            )
        if performance_item.equity_status in {
            EquityStatus.BELOW_FLOOR,
            EquityStatus.RESTRICTED,
        }:
            findings.append(
                _finding(
                    f"finding.{performance_item.metric_id}.equity",
                    SubgroupFindingCode.SAFETY_FLOOR_BREACH,
                    "Subgroup equity status is outside the configured safety floor.",
                    evidence,
                )
            )
        if (
            performance_item.dimension.value
            in {"rare_biological_state", "low_resource", "pediatric_aya"}
            and performance_item.coverage_status is not CoverageStatus.ADEQUATE
        ):
            findings.append(
                _finding(
                    f"finding.{performance_item.metric_id}.rare",
                    SubgroupFindingCode.RARE_CONTEXT_UNSUPPORTED,
                    "Rare or under-resourced subgroup context is not adequately supported.",
                    evidence,
                )
            )
    findings.extend(
        _finding(
            f"finding.{coverage_item.coverage_id}.status",
            (
                SubgroupFindingCode.UPSTREAM_UNSUPPORTED
                if coverage_item.status is CoverageStatus.UNSUPPORTED
                else SubgroupFindingCode.COVERAGE_LIMITED
            ),
            "Coverage status does not support a safe subgroup evaluation.",
            evidence,
        )
        for coverage_item in request.coverage
        if coverage_item.status in {CoverageStatus.UNSUPPORTED, CoverageStatus.NOT_EVALUABLE}
    )
    findings.extend(
        _finding(
            f"finding.{calibration_item.calibration_id}.calibration",
            SubgroupFindingCode.CALIBRATION_FAILURE,
            "Calibration does not meet the configured nominal coverage target.",
            evidence,
        )
        for calibration_item in request.calibration
        if calibration_item.status is EvaluationStatus.ABSTAINED
        or calibration_item.nominal_coverage < request.configuration.nominal_coverage_target
    )
    return tuple(sorted(findings, key=lambda item: item.finding_id))


def _limitations(*, evaluated: bool) -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="m2105_no_identity_or_treatment",
            statement=(
                "M21-05 does not infer identity, consent, treatment, kinase activity, "
                "or all-omics claims."
            ),
        ),
        Limitation(
            code="m2105_caller_declared_authority",
            statement=(
                "Upstream issuer authority and raw artifact contents are not authenticated here."
            ),
        ),
        Limitation(
            code="m2105_evaluated" if evaluated else "m2105_abstained",
            statement=(
                "Only caller-declared subgroup metrics satisfying the locked policy are evaluated."
                if evaluated
                else (
                    "Unsupported, limited, unsafe, or non-evaluable subgroup material is withheld."
                )
            ),
        ),
    )


class M2105Engine:
    """Stateless deterministic subgroup equity evaluator."""

    def validate_request(self, candidate: object) -> EvaluateComplexActivitySubgroupEquityRequest:
        preflight_m2105_authorization(candidate)
        try:
            return _REQUEST_ADAPTER.validate_python(candidate, strict=True)
        except Exception as error:
            raise M2105EvaluationError("M21-05 request is invalid") from error

    def evaluate(self, candidate: object) -> ComplexActivitySubgroupEvaluationResult:
        request = self.validate_request(candidate)
        request_digest = canonical_request_digest(request)
        evidence = _evidence(request)
        findings = _findings(request, evidence)
        evaluated = not findings
        report = (
            SubgroupEvaluationReport(
                report_id=f"report.{request_digest.removeprefix('sha256:')}",
                version=request.configuration.version,
                performance=request.performance,
                calibration=request.calibration,
                coverage=request.coverage,
                configuration=request.configuration,
                evidence=evidence,
            )
            if evaluated
            else None
        )
        status = EvaluationStatus.EVALUATED if report is not None else EvaluationStatus.ABSTAINED
        support = SupportDecision(
            status=SupportStatus.SUPPORTED
            if evaluated
            else (
                SupportStatus.UNSUPPORTED
                if any(item.code is SubgroupFindingCode.UPSTREAM_UNSUPPORTED for item in findings)
                else SupportStatus.REVIEW_REQUIRED
            ),
            reason_code="m2105_evaluated" if evaluated else "m2105_review_required",
            rationale=(
                "All subgroup dimensions meet the caller-declared evaluation policy."
                if evaluated
                else (
                    "Subgroup evidence cannot be safely promoted beyond the declared "
                    "support envelope."
                )
            ),
        )
        payload: dict[str, Any] = {
            "output_type": "complex_activity_subgroup_evaluation",
            "result_id": f"result.{request_digest.removeprefix('sha256:')}",
            "result_version": M2105_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": status,
            "report": report,
            "findings": findings,
            "abstention_reason": (
                None
                if evaluated
                else "M21-05 abstained because subgroup equity evidence is not safely evaluable."
            ),
            "parent_target": "complex activity",
            "emits_parent": False,
            "support_decision": support,
            "uncertainty": _uncertainty(evaluated=evaluated),
            "provenance": _provenance(request, request_digest),
            "evidence": evidence,
            "limitations": _limitations(evaluated=evaluated),
            "human_review_required": not evaluated,
        }
        constructed = ComplexActivitySubgroupEvaluationResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(constructed)
        try:
            return _RESULT_ADAPTER.validate_python(payload, strict=True)
        except Exception as error:
            raise M2105EvaluationError("M21-05 result construction failed safely") from error

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ComplexActivitySubgroupEvaluationResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M2105ReplayError("M21-05 result is invalid") from error
        if validated.result_digest != result_payload_digest(validated):
            raise M2105ReplayError("M21-05 result digest mismatch")
        if replay:
            expected = self.evaluate(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M2105ReplayError("M21-05 deterministic replay mismatch")
        return validated


def evaluate_complex_activity_subgroup_equity(
    candidate: object,
) -> ComplexActivitySubgroupEvaluationResult:
    """Public M21-05 evaluation operation."""

    return M2105Engine().evaluate(candidate)


__all__ = [
    "M2105AuthorizationError",
    "M2105Engine",
    "M2105EvaluationError",
    "M2105ReplayError",
    "evaluate_complex_activity_subgroup_equity",
    "preflight_m2105_authorization",
    "result_payload_digest",
]
