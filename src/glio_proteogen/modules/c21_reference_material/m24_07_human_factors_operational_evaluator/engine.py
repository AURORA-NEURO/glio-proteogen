"""Deterministic, caller-declared M24-07 operational evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m24_07 import (
    M2407_CONTRACT_VERSION,
    M2407_EVIDENCE_CLAIM,
    M2407_MODULE_ID,
    BiomarkerPanelHumanFactorsResult,
    EvaluateBiomarkerPanelHumanFactorsRequest,
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
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import (
    ArtifactReference,
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

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateBiomarkerPanelHumanFactorsRequest)
_AUTHORIZATION_MESSAGE: Final = (
    "M24-07 evaluation requires accepted configuration, resolved identity, granted consent, "
    "accepted provenance/quality/support/intended-use controls"
)
_LIMITATIONS: Final = (
    Limitation(
        code="caller_declared_operational_material",
        statement=(
            "Operational metrics, thresholds, fallback paths and evidence are caller-declared; "
            "issuer authority, user comprehension and scientific correctness are not authenticated."
        ),
    ),
    Limitation(
        code="biomarker_panel_parent_boundary",
        statement=(
            "The evaluator reports human-factors and operational validation material but does not "
            "emit a biomarker panel, subtype, treatment recommendation or biological conclusion."
        ),
    ),
    Limitation(
        code="exclusive_scope",
        statement=(
            "KINOPHOS kinase ownership, generic all-omics fusion, treatment recommendation, "
            "identity inference, consent inference and unsupported-to-negative conversion are "
            "outside this module."
        ),
    ),
)


class M2407AuthorizationError(ValueError):
    """Raised when caller-declared controls do not authorize evaluation."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class M2407ReplayError(ValueError):
    """Raised when an immutable M24-07 result fails replay closure."""


class M2407HumanFactorsOperationalEvaluator:
    """Evaluate one locked operational report and preserve safe failure."""

    __slots__ = ()

    def evaluate(self, request: object) -> BiomarkerPanelHumanFactorsResult:
        if isinstance(request, bytes | bytearray | str):
            validated = _REQUEST_ADAPTER.validate_json(request, strict=True)
            preflight_m2407_authorization(validated)
        else:
            preflight_m2407_authorization(request)
            validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        canonical = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(validated), strict=True)
        request_digest = canonical_request_digest(canonical)
        findings = _findings(canonical)
        report = None
        if not findings:
            report = _report(canonical, request_digest)
        supported = not findings
        payload: dict[str, Any] = {
            "output_type": "biomarker_panel_human_factors_operational",
            "result_id": result_identifier(canonical),
            "result_version": M2407_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": "sha256:" + "0" * 64,
            "request": canonical,
            "status": EvaluationStatus.EVALUATED if supported else EvaluationStatus.ABSTAINED,
            "report": report,
            "findings": findings,
            "abstention_reason": None if supported else _abstention_reason(findings),
            "parent_target": "biomarker panel",
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED if supported else SupportStatus.REVIEW_REQUIRED,
                reason_code=(
                    "operational_evaluation_complete"
                    if supported
                    else "operational_review_required"
                ),
                rationale=(
                    "All seven human-factors and operational dimensions satisfy the locked "
                    "configuration."
                    if supported
                    else "One or more operational, fallback or human-review gates require review."
                ),
            ),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(canonical, request_digest),
            "evidence": _evidence(canonical),
            "limitations": _LIMITATIONS,
            "human_review_required": True,
        }
        provisional = BiomarkerPanelHumanFactorsResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(provisional)
        return BiomarkerPanelHumanFactorsResult.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )

    def verify_replay(
        self,
        result: BiomarkerPanelHumanFactorsResult,
    ) -> BiomarkerPanelHumanFactorsResult:
        """Re-evaluate the bound request and compare every result region."""

        if result.request_digest != canonical_request_digest(result.request):
            raise M2407ReplayError("M24-07 result request digest mismatch")  # noqa: TRY003
        if result.result_id != result_identifier(result.request):
            raise M2407ReplayError("M24-07 result identifier mismatch")  # noqa: TRY003
        if result.result_digest != result_payload_digest(result):
            raise M2407ReplayError("M24-07 result payload digest mismatch")  # noqa: TRY003
        try:
            replayed = BiomarkerPanelHumanFactorsResult.model_validate_json(
                canonical_json_bytes(result), strict=True
            )
            expected = self.evaluate(replayed.request)
        except Exception as error:
            raise M2407ReplayError from error
        if canonical_json_bytes(expected) != canonical_json_bytes(replayed):
            raise M2407ReplayError("M24-07 semantic replay mismatch")  # noqa: TRY003
        return replayed


def evaluate_biomarker_panel_human_factors_operational(
    request: object,
) -> BiomarkerPanelHumanFactorsResult:
    """Public stateless M24-07 evaluation entry point."""

    return M2407HumanFactorsOperationalEvaluator().evaluate(request)


def preflight_m2407_authorization(candidate: object) -> None:
    """Reject denied controls before traversing caller-declared operational material."""

    try:
        context = (
            candidate.context
            if isinstance(candidate, EvaluateBiomarkerPanelHumanFactorsRequest)
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
            _state_value(_member(_member(references, role), "state")) == state
            for role, state in expected.items()
        )
    except Exception:  # noqa: BLE001 - fail closed at hostile mapping boundary.
        raise M2407AuthorizationError from None
    if not authorized:
        raise M2407AuthorizationError


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state_value(candidate: object) -> object:
    return getattr(candidate, "value", candidate)


def _findings(
    request: EvaluateBiomarkerPanelHumanFactorsRequest,
) -> tuple[OperationalFinding, ...]:
    findings: list[OperationalFinding] = []
    evidence = _evidence(request)
    for metric in request.metrics:
        code = {
            OperationalDimension.REVIEWER_COMPREHENSION: (
                OperationalFindingCode.COMPREHENSION_FAILURE
            ),
            OperationalDimension.AUTOMATION_BIAS: OperationalFindingCode.AUTOMATION_BIAS_RISK,
            OperationalDimension.THROUGHPUT: OperationalFindingCode.THROUGHPUT_FAILURE,
            OperationalDimension.LATENCY: OperationalFindingCode.LATENCY_FAILURE,
            OperationalDimension.DOWNTIME: OperationalFindingCode.DOWNTIME_FAILURE,
            OperationalDimension.RECOVERY: OperationalFindingCode.RECOVERY_FAILURE,
            OperationalDimension.FALLBACK: OperationalFindingCode.FALLBACK_UNAVAILABLE,
        }[metric.dimension]
        if metric.status is not OperationalStatus.PASS:
            findings.append(
                OperationalFinding(
                    finding_id="m2407.metric." + metric.metric_id,
                    code=code,
                    message=(
                        f"{metric.metric_name} is not evaluable under the locked operational gate."
                    ),
                    evidence=evidence,
                )
            )
    findings.extend(
        OperationalFinding(
            finding_id="m2407.fallback." + scenario.scenario_id,
            code=OperationalFindingCode.FALLBACK_UNAVAILABLE,
            message=f"Fallback scenario {scenario.scenario_id} requires review.",
            evidence=evidence,
        )
        for scenario in request.fallbacks
        if not scenario.fallback_available or scenario.status is not OperationalStatus.PASS
    )
    return tuple(findings)


def _report(
    request: EvaluateBiomarkerPanelHumanFactorsRequest,
    request_digest: str,
) -> HumanFactorsOperationalReport:
    return HumanFactorsOperationalReport(
        report_id="m2407.report." + request_digest.removeprefix("sha256:"),
        version=request.configuration.version,
        metrics=request.metrics,
        fallbacks=request.fallbacks,
        configuration=request.configuration,
        evidence=_evidence(request),
    )


def _abstention_reason(findings: tuple[OperationalFinding, ...]) -> str:
    codes = ", ".join(sorted({finding.code.value for finding in findings}))
    return "M24-07 abstained pending review of: " + codes


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=f"M24-07 does not infer {dimension} uncertainty from caller material.",
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
            "Operational evaluator uncertainty is not clinical efficacy uncertainty.",
        ),
    )


def _evidence(
    request: EvaluateBiomarkerPanelHumanFactorsRequest,
) -> tuple[EvidenceReference, ...]:
    references = request.context.references
    artifacts = list(request.source_artifacts)
    artifacts.extend(
        evidence.reference for metric in request.metrics for evidence in metric.evidence
    )
    artifacts.extend(
        evidence.reference for fallback in request.fallbacks for evidence in fallback.evidence
    )
    artifacts.extend(evidence.reference for evidence in request.configuration.evidence)
    artifacts.extend(
        (
            references.approved_configuration.evidence,
            references.identity_lineage.evidence,
            references.provenance.evidence,
            references.consent.evidence,
            references.quality.evidence,
            references.support.evidence,
            references.intended_use.evidence,
        )
    )
    unique: dict[str, ArtifactReference] = {}
    for artifact in artifacts:
        unique.setdefault(artifact.digest, artifact)
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M2407_EVIDENCE_CLAIM)
        for artifact in tuple(unique.values())[:64]
    )


def _provenance(
    request: EvaluateBiomarkerPanelHumanFactorsRequest,
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
    emitted_evidence = _evidence(request)
    input_digests = tuple(
        dict.fromkeys(
            (
                request_digest,
                request.upstream_result.digest,
                *(artifact.digest for artifact in request.source_artifacts),
                *(item.reference.digest for item in emitted_evidence),
            )
        )
    )
    return ProvenanceRecord(
        activity_id="m2407.activity." + request_digest.removeprefix("sha256:"),
        actor_id=request.context.actor_id,
        module_id=M2407_MODULE_ID,
        module_version=M2407_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=canonical_request_digest(request.configuration),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=decisions,
    )


__all__ = [
    "M2407AuthorizationError",
    "M2407HumanFactorsOperationalEvaluator",
    "M2407ReplayError",
    "evaluate_biomarker_panel_human_factors_operational",
    "preflight_m2407_authorization",
]
