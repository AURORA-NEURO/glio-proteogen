"""Deterministic metadata-only M24-04 transport evaluation runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m24_04 import (
    M2404_CONTRACT_VERSION,
    M2404_EVIDENCE_CLAIM,
    M2404_MODULE_ID,
    BiomarkerPanelExternalTransportResult,
    EvaluateBiomarkerPanelExternalTransportRequest,
    EvaluationStatus,
    SupportDomainUpdate,
    TransportabilityReport,
    TransportFinding,
    TransportFindingCode,
    TransportStatus,
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

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateBiomarkerPanelExternalTransportRequest)
_AUTHORIZATION_MESSAGE: Final = (
    "M24-04 transport evaluation requires accepted configuration, resolved identity, granted "
    "consent, and accepted provenance/quality/support/intended-use controls"
)
_LIMITATIONS: Final = (
    Limitation(
        code="caller_declared_transport",
        statement=(
            "Transport inputs, validation records, calibration metrics, and provenance are "
            "caller-declared; issuer authority and scientific content are not authenticated."
        ),
    ),
    Limitation(
        code="support_domain_only",
        statement=(
            "The module reports transport support-domain boundaries and does not make a "
            "biological, diagnostic, prognostic, or treatment claim."
        ),
    ),
    Limitation(
        code="external_transport_scope",
        statement=(
            "Site, lab, platform, treatment-era, population, disease-class, and specimen "
            "dimensions are evaluated independently; unsupported dimensions require review."
        ),
    ),
)


class M2404AuthorizationError(ValueError):
    """Raised when caller-declared controls do not authorize transport evaluation."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class M2404ReplayError(ValueError):
    """Raised when a transport result fails canonical replay verification."""


class M2404ExternalTransportEngine:
    """Build and replay one deterministic external transport report."""

    __slots__ = ()

    def generate(self, request: object) -> BiomarkerPanelExternalTransportResult:
        preflight_m2404_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        canonical = _REQUEST_ADAPTER.validate_json(
            canonical_json_bytes(validated.model_dump(mode="json")), strict=True
        )
        request_digest = canonical_request_digest(canonical)
        if _contains_not_evaluable(canonical):
            return _result(
                canonical,
                request_digest,
                status=EvaluationStatus.ABSTAINED,
                report=None,
                findings=(),
                abstention_reason=(
                    "At least one transport dimension is not evaluable; M24-04 abstains "
                    "without converting missing transport evidence into a negative claim."
                ),
                support_status=SupportStatus.REVIEW_REQUIRED,
            )
        narrowed = any(
            evaluation.status is TransportStatus.DOMAIN_NARROWED
            for evaluation in canonical.evaluations
        )
        if narrowed:
            return _result(
                canonical,
                request_digest,
                status=EvaluationStatus.ABSTAINED,
                report=None,
                findings=_findings(canonical),
                abstention_reason=(
                    "One or more external transport dimensions failed calibration; support "
                    "domain is narrowed and requires human review."
                ),
                support_status=SupportStatus.REVIEW_REQUIRED,
            )
        report = _report(canonical, request_digest)
        return _result(
            canonical,
            request_digest,
            status=EvaluationStatus.EVALUATED,
            report=report,
            findings=_findings(canonical),
            abstention_reason=None,
            support_status=SupportStatus.SUPPORTED,
        )

    def replay(
        self,
        result: BiomarkerPanelExternalTransportResult,
    ) -> BiomarkerPanelExternalTransportResult:
        if result.request_digest != canonical_request_digest(result.request):
            raise M2404ReplayError("M24-04 result request digest mismatch")  # noqa: TRY003
        if result.result_id != result_identifier(result.request):
            raise M2404ReplayError("M24-04 result identifier mismatch")  # noqa: TRY003
        if result.result_digest != result_payload_digest(result):
            raise M2404ReplayError("M24-04 result payload digest mismatch")  # noqa: TRY003
        return BiomarkerPanelExternalTransportResult.model_validate_json(
            canonical_json_bytes(result.model_dump(mode="json")), strict=True
        )


def evaluate_biomarker_panel_external_transport(
    request: object,
) -> BiomarkerPanelExternalTransportResult:
    """Run the public deterministic M24-04 operation."""

    return M2404ExternalTransportEngine().generate(request)


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state_value(candidate: object) -> object:
    actual = _member(candidate, "state")
    return getattr(actual, "value", actual)


def preflight_m2404_authorization(candidate: object) -> None:
    """Fail closed before reading transport metadata or scientific payloads."""

    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        decisions = (
            _member(references, "approved_configuration"),
            _member(references, "identity_lineage"),
            _member(references, "provenance"),
            _member(references, "consent"),
            _member(references, "quality"),
            _member(references, "support"),
            _member(references, "intended_use"),
        )
        if any(decision is None for decision in decisions):
            raise M2404AuthorizationError  # noqa: TRY301
        if _state_value(decisions[0]) != UpstreamDecisionState.ACCEPTED.value:
            raise M2404AuthorizationError  # noqa: TRY301
        if _state_value(decisions[1]) != IdentityLineageState.RESOLVED.value:
            raise M2404AuthorizationError  # noqa: TRY301
        if _state_value(decisions[2]) != UpstreamDecisionState.ACCEPTED.value:
            raise M2404AuthorizationError  # noqa: TRY301
        if _state_value(decisions[3]) != ConsentState.GRANTED.value:
            raise M2404AuthorizationError  # noqa: TRY301
        if any(
            _state_value(decision) != UpstreamDecisionState.ACCEPTED.value
            for decision in decisions[4:]
        ):
            raise M2404AuthorizationError  # noqa: TRY301
    except M2404AuthorizationError:
        raise
    except Exception as error:
        raise M2404AuthorizationError from error


def _contains_not_evaluable(
    request: EvaluateBiomarkerPanelExternalTransportRequest,
) -> bool:
    return any(
        evaluation.status is TransportStatus.NOT_EVALUABLE for evaluation in request.evaluations
    )


def _report(
    request: EvaluateBiomarkerPanelExternalTransportRequest,
    request_digest: str,
) -> TransportabilityReport:
    retained = tuple(
        evaluation.dimension
        for evaluation in request.evaluations
        if evaluation.status is TransportStatus.SUPPORTED
    )
    narrowed = tuple(
        evaluation.dimension
        for evaluation in request.evaluations
        if evaluation.status is TransportStatus.DOMAIN_NARROWED
    )
    status = TransportStatus.DOMAIN_NARROWED if narrowed else TransportStatus.SUPPORTED
    return TransportabilityReport(
        report_id="m2404.report." + request_digest.removeprefix("sha256:"),
        version=request.configuration.version,
        validations=request.validations,
        evaluations=request.evaluations,
        support_domain=SupportDomainUpdate(
            update_id="m2404.support-domain." + request_digest.removeprefix("sha256:"),
            version=request.configuration.version,
            status=status,
            retained_dimensions=retained or (request.configuration.required_dimensions[0],),
            narrowed_dimensions=narrowed,
            rationale=(
                "All configured transport dimensions meet their calibration floors."
                if not narrowed
                else "Failed calibration dimensions are excluded from the supported domain."
            ),
            evidence=_evidence(request),
        ),
        configuration=request.configuration,
        evidence=_evidence(request),
    )


def _findings(
    request: EvaluateBiomarkerPanelExternalTransportRequest,
) -> tuple[TransportFinding, ...]:
    findings: list[TransportFinding] = []
    findings.extend(
        TransportFinding(
            finding_id=f"{evaluation.evaluation_id}.calibration-floor",
            code=TransportFindingCode.CALIBRATION_FLOOR_FAILED,
            message=(
                f"Transport dimension {evaluation.dimension.value} failed its calibration floor."
            ),
            evidence=_evidence(request),
        )
        for evaluation in request.evaluations
        if evaluation.status is TransportStatus.DOMAIN_NARROWED
    )
    findings.extend(
        TransportFinding(
            finding_id=f"{evaluation.evaluation_id}.not-evaluable",
            code=TransportFindingCode.EVALUATION_INCOMPLETE,
            message=(f"Transport dimension {evaluation.dimension.value} is not evaluable."),
            evidence=_evidence(request),
        )
        for evaluation in request.evaluations
        if evaluation.status is TransportStatus.NOT_EVALUABLE
    )
    return tuple(findings)


def _result(  # noqa: PLR0913
    request: EvaluateBiomarkerPanelExternalTransportRequest,
    request_digest: str,
    *,
    status: EvaluationStatus,
    report: TransportabilityReport | None,
    findings: tuple[TransportFinding, ...],
    abstention_reason: str | None,
    support_status: SupportStatus,
) -> BiomarkerPanelExternalTransportResult:
    payload: dict[str, Any] = {
        "output_type": "biomarker_panel_external_transport",
        "result_id": result_identifier(request),
        "result_version": M2404_CONTRACT_VERSION,
        "request_digest": request_digest,
        "result_digest": "sha256:" + ("0" * 64),
        "request": request,
        "status": status,
        "report": report,
        "findings": findings,
        "abstention_reason": abstention_reason,
        "parent_target": "biomarker panel",
        "emits_parent": False,
        "support_decision": _support(support_status),
        "uncertainty": _uncertainty(),
        "provenance": _provenance(request, request_digest),
        "evidence": _evidence(request),
        "limitations": _LIMITATIONS,
        "human_review_required": True,
    }
    provisional = BiomarkerPanelExternalTransportResult.model_construct(**payload)
    payload["result_digest"] = result_payload_digest(provisional)
    return BiomarkerPanelExternalTransportResult.model_validate_json(
        canonical_json_bytes(payload), strict=True
    )


def _support(status: SupportStatus) -> SupportDecision:
    return SupportDecision(
        status=status,
        reason_code=(
            "transport_evaluation_completed"
            if status is SupportStatus.SUPPORTED
            else "transport_domain_requires_review"
        ),
        rationale=(
            "All caller-declared transport dimensions meet the locked calibration criteria."
            if status is SupportStatus.SUPPORTED
            else "At least one transport dimension is unsupported or requires human review."
        ),
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=(
                f"M24-04 does not estimate {dimension} uncertainty from metadata-only inputs."
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
            "Transport evidence is caller-declared and does not establish biological uncertainty.",
        ),
    )


def _evidence(
    request: EvaluateBiomarkerPanelExternalTransportRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M2404_EVIDENCE_CLAIM)
        for artifact in request.source_artifacts
    )


def _provenance(
    request: EvaluateBiomarkerPanelExternalTransportRequest,
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
        activity_id="m2404.activity." + request_digest.removeprefix("sha256:"),
        actor_id=request.context.actor_id,
        module_id=M2404_MODULE_ID,
        module_version=M2404_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(artifact.digest for artifact in request.source_artifacts),
        configuration_digest=sha256_digest(
            {"configuration": request.configuration, "evaluations": request.evaluations}
        ),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=decisions,
    )


__all__ = [
    "M2404AuthorizationError",
    "M2404ExternalTransportEngine",
    "M2404ReplayError",
    "evaluate_biomarker_panel_external_transport",
    "preflight_m2404_authorization",
]
