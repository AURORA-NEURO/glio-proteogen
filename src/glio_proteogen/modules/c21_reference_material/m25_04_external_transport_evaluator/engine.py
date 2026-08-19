"""Deterministic, caller-declared M25-04 external transport evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m25_04 import (
    M2504_CONTRACT_VERSION,
    M2504_MODULE_ID,
    EvaluateProteotypeExternalTransportRequest,
    EvaluationStatus,
    ProteotypeExternalTransportResult,
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

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateProteotypeExternalTransportRequest)
_AUTHORIZATION_MESSAGE: Final = (
    "M25-04 transport evaluation requires accepted configuration, resolved identity, "
    "granted consent, accepted provenance/quality/support/intended-use controls"
)
_LIMITATIONS: Final = (
    Limitation(
        code="caller_declared_transport",
        statement=(
            "Transport, calibration and support-domain material is caller-declared; issuer "
            "authority and source content are not authenticated or traversed."
        ),
    ),
    Limitation(
        code="support_domain_ceiling",
        statement=(
            "The result reports transport support and may narrow the declared domain; it does "
            "not emit a proteotype estimate or biological conclusion."
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


class M2504AuthorizationError(ValueError):
    """Raised when caller-declared controls do not authorize execution."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class M2504ReplayError(ValueError):
    """Raised when an immutable transport result fails canonical replay."""

    def __init__(self, message: str = "M25-04 replay verification failed") -> None:
        super().__init__(message)


class M2504TransportEngine:
    """Evaluate typed transport declarations without traversing upstream payloads."""

    __slots__ = ()

    def evaluate(self, request: object) -> ProteotypeExternalTransportResult:
        preflight_m2504_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        canonical = _REQUEST_ADAPTER.validate_json(
            canonical_json_bytes(validated.model_dump(mode="json")), strict=True
        )
        request_digest = canonical_request_digest(canonical)
        findings = _findings(canonical)
        report = (
            None
            if (
                any(item.code is TransportFindingCode.EVALUATION_INCOMPLETE for item in findings)
                or not any(
                    item.status is TransportStatus.SUPPORTED for item in canonical.evaluations
                )
            )
            else _report(canonical, request_digest)
        )
        status = EvaluationStatus.ABSTAINED if report is None else EvaluationStatus.EVALUATED
        payload: dict[str, Any] = {
            "output_type": "proteotype_external_transport",
            "result_id": result_identifier(canonical, status.value),
            "result_version": M2504_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": "sha256:" + ("0" * 64),
            "request": canonical,
            "status": status,
            "report": report,
            "findings": findings,
            "abstention_reason": (
                None
                if report is not None
                else "External transport was not safely evaluable under the declared controls."
            ),
            "parent_target": "proteotype",
            "emits_parent": False,
            "support_decision": _support(report),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(canonical, request_digest),
            "evidence": _evidence(canonical),
            "limitations": _LIMITATIONS,
            "human_review_required": True,
        }
        provisional = ProteotypeExternalTransportResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(provisional)
        return ProteotypeExternalTransportResult.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )

    def replay(
        self, result: ProteotypeExternalTransportResult
    ) -> ProteotypeExternalTransportResult:
        try:
            replayed = ProteotypeExternalTransportResult.model_validate_json(
                canonical_json_bytes(result), strict=True
            )
        except Exception as error:
            raise M2504ReplayError from error
        if replayed.request_digest != canonical_request_digest(replayed.request):
            raise M2504ReplayError
        if replayed.result_id != result_identifier(replayed.request, replayed.status.value):
            raise M2504ReplayError
        if replayed.result_digest != result_payload_digest(replayed):
            raise M2504ReplayError
        return replayed


def evaluate_proteotype_external_transport(
    request: object,
) -> ProteotypeExternalTransportResult:
    """Public stateless M25-04 transport evaluation entry point."""

    return M2504TransportEngine().evaluate(request)


def preflight_m2504_authorization(candidate: object) -> None:
    """Reject denied controls before reading transport declarations."""

    try:
        context = (
            candidate.context
            if isinstance(candidate, EvaluateProteotypeExternalTransportRequest)
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
        raise M2504AuthorizationError from None
    if not authorized:
        raise M2504AuthorizationError


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state_value(candidate: object) -> object:
    actual = _member(candidate, "state")
    return getattr(actual, "value", actual)


def _findings(
    request: EvaluateProteotypeExternalTransportRequest,
) -> tuple[TransportFinding, ...]:
    evidence = _evidence(request)
    findings: list[TransportFinding] = []
    for evaluation in request.evaluations:
        if evaluation.status is TransportStatus.DOMAIN_NARROWED:
            findings.append(
                TransportFinding(
                    finding_id=f"finding.narrowed.{evaluation.evaluation_id}",
                    code=TransportFindingCode.SUPPORT_DOMAIN_NARROWED,
                    message=(
                        f"Transport dimension {evaluation.dimension.value} is narrower than the "
                        "declared calibration floor."
                    ),
                    evidence=evidence,
                )
            )
        elif evaluation.status is TransportStatus.NOT_EVALUABLE:
            findings.append(
                TransportFinding(
                    finding_id=f"finding.incomplete.{evaluation.evaluation_id}",
                    code=TransportFindingCode.EVALUATION_INCOMPLETE,
                    message=f"Transport dimension {evaluation.dimension.value} is not evaluable.",
                    evidence=evidence,
                )
            )
    return tuple(sorted(findings, key=lambda item: item.finding_id))


def _report(
    request: EvaluateProteotypeExternalTransportRequest,
    request_digest: str,
) -> TransportabilityReport:
    narrowed = tuple(
        evaluation.dimension
        for evaluation in request.evaluations
        if evaluation.status is TransportStatus.DOMAIN_NARROWED
    )
    retained = tuple(
        evaluation.dimension
        for evaluation in request.evaluations
        if evaluation.status is TransportStatus.SUPPORTED
    )
    domain_status = TransportStatus.DOMAIN_NARROWED if narrowed else TransportStatus.SUPPORTED
    return TransportabilityReport(
        report_id="m2504.report." + request_digest.removeprefix("sha256:"),
        version=request.configuration.version,
        validations=request.validations,
        evaluations=request.evaluations,
        support_domain=SupportDomainUpdate(
            update_id="m2504.support." + request_digest.removeprefix("sha256:"),
            version=request.configuration.version,
            status=domain_status,
            retained_dimensions=retained,
            narrowed_dimensions=narrowed,
            rationale=(
                "All declared transport dimensions clear their calibration floors."
                if not narrowed
                else "The support domain is narrowed to dimensions that clear calibration floors."
            ),
            evidence=_evidence(request),
        ),
        configuration=request.configuration,
        evidence=_evidence(request),
    )


def _support(report: TransportabilityReport | None) -> SupportDecision:
    if report is None:
        return SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED,
            reason_code="transport_evaluation_abstained",
            rationale="At least one required transport dimension is not evaluable.",
        )
    if report.support_domain.status is TransportStatus.DOMAIN_NARROWED:
        return SupportDecision(
            status=SupportStatus.LIMITED,
            reason_code="transport_domain_narrowed",
            rationale="Transport support is limited to dimensions clearing the declared floor.",
        )
    return SupportDecision(
        status=SupportStatus.SUPPORTED,
        reason_code="transport_evaluation_completed",
        rationale="All seven caller-declared transport dimensions clear their calibration floors.",
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=f"M25-04 does not estimate {dimension} uncertainty from declarations alone.",
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
            "Transport declarations are caller-declared and do not establish "
            "biological uncertainty.",
        ),
    )


def _evidence(
    request: EvaluateProteotypeExternalTransportRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim=(
                "Caller-declared M25-04 transport artifact; issuer authority is not authenticated."
            ),
        )
        for artifact in request.source_artifacts
    )


def _provenance(
    request: EvaluateProteotypeExternalTransportRequest,
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
        activity_id="m2504.activity." + request_digest.removeprefix("sha256:"),
        actor_id=request.context.actor_id,
        module_id=M2504_MODULE_ID,
        module_version=M2504_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            *tuple(artifact.digest for artifact in request.source_artifacts),
            request.benchmark_package.digest,
            sha256_digest(request.configuration),
        ),
        configuration_digest=sha256_digest(request.configuration),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=decisions,
    )


__all__ = [
    "M2504AuthorizationError",
    "M2504ReplayError",
    "M2504TransportEngine",
    "evaluate_proteotype_external_transport",
    "preflight_m2504_authorization",
]
