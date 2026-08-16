"""Deterministic caller-declared M25-05 subgroup equity runtime.

This engine evaluates only typed subgroup performance, calibration, coverage, and
equity declarations. It does not inspect the M25-04 artifact, infer identity or
consent, run a model, or turn unsupported groups into negative findings.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m25_05 import (
    M2505_CONTRACT_VERSION,
    M2505_MODULE_ID,
    CoverageStatus,
    EquityStatus,
    EvaluateProteotypeSubgroupEquityRequest,
    EvaluationStatus,
    ProteotypeSubgroupEvaluationResult,
    SubgroupEvaluationReport,
    SubgroupFinding,
    SubgroupFindingCode,
    canonical_request_digest,
    result_identifier,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ConsentState,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    IdentityLineageReference,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateProteotypeSubgroupEquityRequest)
_AUTHORIZATION_MESSAGE: Final = (
    "M25-05 evaluation requires accepted configuration, resolved identity, granted consent, "
    "accepted provenance/quality/support/intended-use controls"
)
_LIMITATIONS: Final = (
    Limitation(
        code="caller_declared_upstream",
        statement=(
            "The M25-04 result is caller-declared; issuer authority and scientific payload "
            "content are not authenticated or traversed."
        ),
    ),
    Limitation(
        code="subgroup_metadata_only",
        statement=(
            "The evaluator compares caller-declared subgroup metrics and does not train, "
            "calibrate, or infer a biological model."
        ),
    ),
    Limitation(
        code="equity_not_identity",
        statement=(
            "Subgroup labels are declared evaluation strata; they do not establish identity, "
            "ancestry, diagnosis, treatment, or clinical eligibility."
        ),
    ),
    Limitation(
        code="exclusive_scope",
        statement=(
            "KINOPHOS kinase ownership, generic all-omics fusion, treatment recommendation, "
            "identity inference, and unsupported-to-negative conversion are outside this module."
        ),
    ),
)


class M2505AuthorizationError(ValueError):
    """Raised when caller-declared controls do not authorize evaluation."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class M2505ReplayError(ValueError):
    """Raised when an immutable M25-05 result fails canonical replay."""

    def __init__(self, message: str = "M25-05 replay verification failed") -> None:
        super().__init__(message)


class M2505SubgroupEquityEngine:
    """Build and replay one deterministic subgroup equity evaluation."""

    __slots__ = ()

    def generate(self, request: object) -> ProteotypeSubgroupEvaluationResult:
        preflight_m2505_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        canonical = _REQUEST_ADAPTER.validate_json(
            canonical_json_bytes(validated.model_dump(mode="json")), strict=True
        )
        request_digest = canonical_request_digest(canonical)
        findings = _findings(canonical)
        report = None if findings else _report(canonical)
        status = EvaluationStatus.EVALUATED if report is not None else EvaluationStatus.ABSTAINED
        payload: dict[str, Any] = {
            "output_type": "proteotype_subgroup_evaluation",
            "result_id": result_identifier(canonical, status.value),
            "result_version": M2505_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": "sha256:" + ("0" * 64),
            "request": canonical,
            "status": status,
            "report": report,
            "findings": findings,
            "abstention_reason": None
            if report is not None
            else "Subgroup equity was not safely evaluable under the declared controls.",
            "parent_target": "proteotype",
            "emits_parent": False,
            "support_decision": _support(completed=report is not None),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(canonical, request_digest),
            "evidence": _evidence(canonical),
            "limitations": _LIMITATIONS,
            "human_review_required": report is None,
        }
        provisional = ProteotypeSubgroupEvaluationResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(provisional)
        return ProteotypeSubgroupEvaluationResult.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )

    def replay(
        self,
        result: ProteotypeSubgroupEvaluationResult,
    ) -> ProteotypeSubgroupEvaluationResult:
        try:
            replayed = ProteotypeSubgroupEvaluationResult.model_validate_json(
                canonical_json_bytes(result), strict=True
            )
        except Exception as error:
            raise M2505ReplayError from error
        if replayed.request_digest != canonical_request_digest(replayed.request):
            raise M2505ReplayError
        if replayed.result_id != result_identifier(replayed.request, replayed.status.value):
            raise M2505ReplayError
        if replayed.result_digest != result_payload_digest(replayed):
            raise M2505ReplayError
        return replayed


def evaluate_proteotype_subgroup_equity(
    request: object,
) -> ProteotypeSubgroupEvaluationResult:
    """Public stateless M25-05 evaluation entry point."""

    return M2505SubgroupEquityEngine().generate(request)


def preflight_m2505_authorization(candidate: object) -> None:
    """Reject denied controls before reading subgroup declarations."""

    try:
        context = (
            candidate.context
            if isinstance(candidate, EvaluateProteotypeSubgroupEquityRequest)
            else candidate.get("context")
            if isinstance(candidate, Mapping)
            else None
        )
        references = _member(context, "references")
        expected = {
            "approved_configuration": UpstreamDecisionState.ACCEPTED.value,
            "identity_lineage": IdentityLineageState.RESOLVED.value,
            "provenance": UpstreamDecisionState.ACCEPTED.value,
            "consent": ConsentState.GRANTED.value,
            "quality": UpstreamDecisionState.ACCEPTED.value,
            "support": UpstreamDecisionState.ACCEPTED.value,
            "intended_use": UpstreamDecisionState.ACCEPTED.value,
        }
        authorized = all(
            _state_value(_member(references, role)) == state for role, state in expected.items()
        )
    except Exception:  # noqa: BLE001 - fail closed at hostile mapping boundary.
        raise M2505AuthorizationError from None
    if not authorized:
        raise M2505AuthorizationError


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state_value(candidate: object) -> object:
    actual = _member(candidate, "state")
    return getattr(actual, "value", actual)


def _findings(
    request: EvaluateProteotypeSubgroupEquityRequest,
) -> tuple[SubgroupFinding, ...]:
    evidence = _evidence(request)
    findings: list[SubgroupFinding] = []
    findings.extend(
        SubgroupFinding(
            finding_id=f"finding.floor.{metric.metric_id}",
            code=SubgroupFindingCode.SAFETY_FLOOR_BREACH,
            message=f"Subgroup metric {metric.metric_id} is below its safety floor.",
            evidence=evidence,
        )
        for metric in request.performance
        if metric.equity_status is EquityStatus.BELOW_FLOOR
    )
    findings.extend(
        SubgroupFinding(
            finding_id=f"finding.coverage.{summary.coverage_id}",
            code=(
                SubgroupFindingCode.COVERAGE_LIMITED
                if summary.status is CoverageStatus.LIMITED
                else SubgroupFindingCode.RARE_CONTEXT_UNSUPPORTED
            ),
            message=f"Coverage declaration {summary.coverage_id} is not adequate.",
            evidence=evidence,
        )
        for summary in request.coverage
        if summary.status is not CoverageStatus.ADEQUATE
    )
    findings.extend(
        SubgroupFinding(
            finding_id=f"finding.calibration.{summary.calibration_id}",
            code=SubgroupFindingCode.CALIBRATION_FAILURE,
            message=f"Calibration declaration {summary.calibration_id} is not evaluable.",
            evidence=evidence,
        )
        for summary in request.calibration
        if summary.status is not EvaluationStatus.EVALUATED
    )
    return tuple(sorted(findings, key=lambda item: item.finding_id))


def _report(request: EvaluateProteotypeSubgroupEquityRequest) -> SubgroupEvaluationReport:
    digest = canonical_request_digest(request)
    return SubgroupEvaluationReport(
        report_id="m2505.report." + digest.removeprefix("sha256:"),
        version=request.configuration.version,
        performance=request.performance,
        calibration=request.calibration,
        coverage=request.coverage,
        configuration=request.configuration,
        evidence=_evidence(request),
    )


def _support(*, completed: bool) -> SupportDecision:
    if completed:
        return SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="subgroup_equity_completed",
            rationale=(
                "Caller-declared performance, calibration, coverage, and safety-floor controls "
                "satisfy the provisional M25-05 boundary."
            ),
        )
    return SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code="subgroup_equity_abstained",
        rationale="A subgroup control is not passing and is withheld for review.",
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=(
                f"M25-05 does not estimate {dimension} uncertainty from metadata-only inputs."
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
            "Subgroup labels and metrics are caller-declared; they do not establish biological "
            "or clinical uncertainty.",
        ),
    )


def _evidence(
    request: EvaluateProteotypeSubgroupEquityRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim=(
                "Caller-declared M25-05 subgroup artifact; issuer authority is not authenticated."
            ),
        )
        for artifact in request.source_artifacts
    )


def _provenance(
    request: EvaluateProteotypeSubgroupEquityRequest,
    request_digest: str,
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
            state=str(decision.state.value),
            policy_version=decision.policy_version,
            evidence_digest=decision.evidence.digest,
            subject_digest=(
                decision.binding_digest if isinstance(decision, IdentityLineageReference) else None
            ),
        )
        for role, decision in controls
    )
    return ProvenanceRecord(
        activity_id="m2505.activity." + request_digest.removeprefix("sha256:"),
        actor_id=request.context.actor_id,
        module_id=M2505_MODULE_ID,
        module_version=M2505_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            *tuple(artifact.digest for artifact in request.source_artifacts),
            request.upstream_result.digest,
            sha256_digest(request.configuration),
        ),
        configuration_digest=sha256_digest(
            {
                "configuration": request.configuration,
                "performance": request.performance,
                "calibration": request.calibration,
                "coverage": request.coverage,
            }
        ),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=decisions,
    )


__all__ = [
    "M2505AuthorizationError",
    "M2505ReplayError",
    "M2505SubgroupEquityEngine",
    "evaluate_proteotype_subgroup_equity",
    "preflight_m2505_authorization",
]
