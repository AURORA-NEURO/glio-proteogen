"""Deterministic, caller-declared M24-05 subgroup equity evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m24_05 import (
    M2405_CONTRACT_VERSION,
    M2405_EVIDENCE_CLAIM,
    M2405_MODULE_ID,
    BiomarkerPanelSubgroupEvaluationResult,
    CoverageStatus,
    EquityStatus,
    EvaluateBiomarkerPanelSubgroupEquityRequest,
    EvaluationStatus,
    SubgroupDimension,
    SubgroupEvaluationReport,
    SubgroupFinding,
    SubgroupFindingCode,
    canonical_request_digest,
    result_identifier,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
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

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateBiomarkerPanelSubgroupEquityRequest)
_AUTHORIZATION_MESSAGE: Final = (
    "M24-05 evaluation requires accepted configuration, resolved identity, granted consent, "
    "accepted provenance/quality/support/intended-use controls"
)
_LIMITATIONS: Final = (
    Limitation(
        code="caller_declared_equity_material",
        statement=(
            "Subgroup metrics, calibration, coverage, floors, architecture labels and evidence "
            "are caller-declared; issuer authority and scientific correctness are not "
            "authenticated."
        ),
    ),
    Limitation(
        code="biomarker_panel_parent_boundary",
        statement=(
            "The evaluator reports subgroup safety and coverage material for a biomarker-panel "
            "workflow but does not emit a biomarker panel or biological conclusion."
        ),
    ),
    Limitation(
        code="exclusive_scope",
        statement=(
            "Kinase ownership, generic all-omics fusion, treatment recommendation, identity "
            "inference, consent inference and unsupported-to-negative conversion are outside "
            "this module."
        ),
    ),
)


class M2405AuthorizationError(ValueError):
    """Raised when caller-declared controls do not authorize evaluation."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class M2405ReplayError(ValueError):
    """Raised when an immutable M24-05 result fails replay closure."""


class M2405SubgroupEquityEvaluator:
    """Evaluate one deterministic subgroup report and preserve safe failure."""

    __slots__ = ()

    def evaluate(self, request: object) -> BiomarkerPanelSubgroupEvaluationResult:
        preflight_m2405_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        canonical = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(validated), strict=True)
        request_digest = canonical_request_digest(canonical)
        findings = _findings(canonical)
        report = (
            SubgroupEvaluationReport(
                report_id="m2405.report." + request_digest.removeprefix("sha256:"),
                version=canonical.configuration.version,
                performance=canonical.performance,
                calibration=canonical.calibration,
                coverage=canonical.coverage,
                configuration=canonical.configuration,
                evidence=_evidence(canonical),
            )
            if not findings
            else None
        )
        supported = not findings
        payload: dict[str, Any] = {
            "output_type": "biomarker_panel_subgroup_evaluation",
            "result_id": result_identifier(canonical),
            "result_version": M2405_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": "sha256:" + ("0" * 64),
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
                    "subgroup_evaluation_complete" if supported else "subgroup_review_required"
                ),
                rationale=(
                    "All eight subgroup dimensions satisfy the locked equity and coverage gates."
                    if supported
                    else (
                        "One or more subgroup safety, coverage, calibration or rare-context "
                        "gates require review."
                    )
                ),
            ),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(canonical, request_digest),
            "evidence": _evidence(canonical),
            "limitations": _LIMITATIONS,
            "human_review_required": not supported,
        }
        provisional = BiomarkerPanelSubgroupEvaluationResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(provisional)
        return BiomarkerPanelSubgroupEvaluationResult.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )

    def verify_replay(
        self,
        result: BiomarkerPanelSubgroupEvaluationResult,
    ) -> BiomarkerPanelSubgroupEvaluationResult:
        if result.request_digest != canonical_request_digest(result.request):
            raise M2405ReplayError("M24-05 result request digest mismatch")  # noqa: TRY003
        if result.result_id != result_identifier(result.request):
            raise M2405ReplayError("M24-05 result identifier mismatch")  # noqa: TRY003
        if result.result_digest != result_payload_digest(result):
            raise M2405ReplayError("M24-05 result payload digest mismatch")  # noqa: TRY003
        return BiomarkerPanelSubgroupEvaluationResult.model_validate_json(
            canonical_json_bytes(result), strict=True
        )


def evaluate_biomarker_panel_subgroup_equity(
    request: object,
) -> BiomarkerPanelSubgroupEvaluationResult:
    """Public stateless M24-05 evaluation entry point."""

    return M2405SubgroupEquityEvaluator().evaluate(request)


def preflight_m2405_authorization(candidate: object) -> None:
    """Reject denied controls before traversing caller-declared metrics."""

    try:
        context = (
            candidate.context
            if isinstance(candidate, EvaluateBiomarkerPanelSubgroupEquityRequest)
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
        raise M2405AuthorizationError from None
    if not authorized:
        raise M2405AuthorizationError


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state_value(candidate: object) -> object:
    return getattr(candidate, "value", candidate)


def _findings(
    request: EvaluateBiomarkerPanelSubgroupEquityRequest,
) -> tuple[SubgroupFinding, ...]:
    findings: list[SubgroupFinding] = []
    evidence = _evidence(request)
    findings.extend(
        [
            SubgroupFinding(
                finding_id="m2405.floor." + performance.metric_id,
                code=SubgroupFindingCode.SAFETY_FLOOR_BREACH,
                message=f"{performance.subgroup} is below the configured safety floor.",
                evidence=evidence,
            )
            for performance in request.performance
            if performance.equity_status is EquityStatus.BELOW_FLOOR
        ]
    )
    for coverage in request.coverage:
        rare = coverage.dimension is SubgroupDimension.RARE_BIOLOGICAL_STATE
        if coverage.status in {CoverageStatus.UNSUPPORTED, CoverageStatus.NOT_EVALUABLE}:
            code = (
                SubgroupFindingCode.RARE_CONTEXT_UNSUPPORTED
                if rare
                else SubgroupFindingCode.COVERAGE_LIMITED
            )
            findings.append(
                SubgroupFinding(
                    finding_id="m2405.coverage." + coverage.coverage_id,
                    code=code,
                    message=f"{coverage.subgroup} does not have evaluable support coverage.",
                    evidence=evidence,
                )
            )
        elif rare and coverage.status is not CoverageStatus.ADEQUATE:
            findings.append(
                SubgroupFinding(
                    finding_id="m2405.rare." + coverage.coverage_id,
                    code=SubgroupFindingCode.RARE_CONTEXT_UNSUPPORTED,
                    message="Rare biological context requires adequate coverage before evaluation.",
                    evidence=evidence,
                )
            )
    findings.extend(
        [
            SubgroupFinding(
                finding_id="m2405.calibration." + calibration.calibration_id,
                code=SubgroupFindingCode.CALIBRATION_FAILURE,
                message=f"{calibration.subgroup} calibration is not evaluable.",
                evidence=evidence,
            )
            for calibration in request.calibration
            if calibration.status is EvaluationStatus.ABSTAINED
        ]
    )
    return tuple(findings)


def _abstention_reason(findings: tuple[SubgroupFinding, ...]) -> str:
    codes = ", ".join(sorted({finding.code.value for finding in findings}))
    return "M24-05 abstained pending review of: " + codes


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=f"M24-05 does not infer {dimension} uncertainty from caller material.",
        )

    return UncertaintyProfile(
        measurement=unavailable("measurement"),
        sampling=unavailable("sampling"),
        parameter=unavailable("parameter"),
        model_form=unavailable("model form"),
        identification=unavailable("identification"),
        support=unavailable("support"),
        transport=unavailable("transport"),
        sensitivity_notes=("Subgroup equity uncertainty is not clinical efficacy uncertainty.",),
    )


def _evidence(
    request: EvaluateBiomarkerPanelSubgroupEquityRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M2405_EVIDENCE_CLAIM)
        for artifact in request.source_artifacts
    )


def _provenance(
    request: EvaluateBiomarkerPanelSubgroupEquityRequest,
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
        activity_id="m2405.activity." + request_digest.removeprefix("sha256:"),
        actor_id=request.context.actor_id,
        module_id=M2405_MODULE_ID,
        module_version=M2405_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(artifact.digest for artifact in request.source_artifacts),
        configuration_digest=canonical_request_digest(request.configuration),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=decisions,
    )


__all__ = [
    "M2405AuthorizationError",
    "M2405ReplayError",
    "M2405SubgroupEquityEvaluator",
    "evaluate_biomarker_panel_subgroup_equity",
    "preflight_m2405_authorization",
]
