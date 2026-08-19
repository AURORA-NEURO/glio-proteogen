"""Deterministic, caller-declared M22-05 subgroup equity evaluation runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m22_05 import (
    M2205_CONTRACT_VERSION,
    M2205_MODULE_ID,
    CoverageStatus,
    EquityStatus,
    EvaluateProteinRnaDiscordanceSubgroupEquityRequest,
    EvaluationStatus,
    ProteinRnaDiscordanceSubgroupEvaluationResult,
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

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateProteinRnaDiscordanceSubgroupEquityRequest)
_AUTHORIZATION_MESSAGE: Final = (
    "M22-05 subgroup evaluation requires accepted configuration, resolved identity, granted "
    "consent, accepted provenance/quality/support/intended-use controls"
)
_LIMITATIONS: Final = (
    Limitation(
        code="caller_declared_upstream",
        statement=(
            "The M22-04 evaluator result is caller-declared; issuer authority and source content "
            "are not authenticated or traversed."
        ),
    ),
    Limitation(
        code="metadata_only_equity",
        statement=(
            "The evaluator reports caller-declared subgroup performance, calibration, coverage, "
            "and equity material; it does not fit a biological or clinical model."
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


class M2205AuthorizationError(ValueError):
    """Raised when caller-declared controls do not authorize evaluation."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class M2205ReplayError(ValueError):
    """Raised when an evaluation result fails canonical replay verification."""

    def __init__(self, message: str = "M22-05 replay verification failed") -> None:
        super().__init__(message)


class M2205EquityEngine:
    """Build and replay one deterministic metadata-only subgroup evaluation."""

    __slots__ = ()

    def generate(self, request: object) -> ProteinRnaDiscordanceSubgroupEvaluationResult:
        preflight_m2205_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        canonical = _REQUEST_ADAPTER.validate_json(
            canonical_json_bytes(validated.model_dump(mode="json")), strict=True
        )
        request_digest = canonical_request_digest(canonical)
        report = SubgroupEvaluationReport(
            report_id="m2205.report." + request_digest.removeprefix("sha256:"),
            version=canonical.configuration.version,
            performance=canonical.performance,
            calibration=canonical.calibration,
            coverage=canonical.coverage,
            configuration=canonical.configuration,
            evidence=_evidence(canonical),
        )
        findings = _findings(canonical)
        unsupported = _abstention_reason(findings)
        if unsupported is None:
            status = EvaluationStatus.EVALUATED
            output_report: SubgroupEvaluationReport | None = report
            abstention_reason: str | None = None
            support = _support()
            human_review_required = False
        else:
            status = EvaluationStatus.ABSTAINED
            output_report = None
            abstention_reason = unsupported
            support = SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="subgroup_coverage_not_evaluable",
                rationale=unsupported,
            )
            human_review_required = True
        payload: dict[str, Any] = {
            "output_type": "protein_rna_discordance_subgroup_evaluation",
            "result_id": result_identifier(canonical),
            "result_version": M2205_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": "sha256:" + ("0" * 64),
            "request": canonical,
            "status": status,
            "report": output_report,
            "findings": findings,
            "abstention_reason": abstention_reason,
            "parent_target": "protein-RNA discordance",
            "emits_parent": False,
            "support_decision": support,
            "uncertainty": _uncertainty(),
            "provenance": _provenance(canonical, request_digest),
            "evidence": _evidence(canonical),
            "limitations": _LIMITATIONS,
            "human_review_required": human_review_required,
        }
        provisional = ProteinRnaDiscordanceSubgroupEvaluationResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(provisional)
        return ProteinRnaDiscordanceSubgroupEvaluationResult.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )

    def replay(
        self,
        result: ProteinRnaDiscordanceSubgroupEvaluationResult,
    ) -> ProteinRnaDiscordanceSubgroupEvaluationResult:
        """Regenerate the result from its bound request before accepting replay.

        A result digest proves only that the supplied envelope is internally
        consistent.  It does not establish that the envelope was produced by
        this evaluator: a caller can modify a finding, report, or evidence
        field and recompute the digest.  Replay therefore validates the
        envelope, regenerates the deterministic result from its request, and
        compares the complete canonical JSON projections.
        """

        try:
            request_digest = canonical_request_digest(result.request)
            result_id = result_identifier(result.request)
            payload_digest = result_payload_digest(result)
        except Exception as error:
            raise M2205ReplayError from error
        if result.request_digest != request_digest:
            raise M2205ReplayError("M22-05 result request digest mismatch")  # noqa: TRY003
        if result.result_id != result_id:
            raise M2205ReplayError("M22-05 result identifier mismatch")  # noqa: TRY003
        if result.result_digest != payload_digest:
            raise M2205ReplayError("M22-05 result payload digest mismatch")  # noqa: TRY003
        try:
            replayed = ProteinRnaDiscordanceSubgroupEvaluationResult.model_validate_json(
                canonical_json_bytes(result), strict=True
            )
            expected = self.generate(replayed.request)
        except Exception as error:
            raise M2205ReplayError from error
        if expected.model_dump(mode="json") != replayed.model_dump(mode="json"):
            raise M2205ReplayError
        return replayed


def evaluate_protein_rna_discordance_subgroup_equity(
    request: object,
) -> ProteinRnaDiscordanceSubgroupEvaluationResult:
    """Public stateless M22-05 evaluation entry point."""

    return M2205EquityEngine().generate(request)


def preflight_m2205_authorization(candidate: object) -> None:
    """Reject denied controls before reading subgroup material."""

    try:
        context = (
            candidate.context
            if isinstance(candidate, EvaluateProteinRnaDiscordanceSubgroupEquityRequest)
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
        raise M2205AuthorizationError from None
    if not authorized:
        raise M2205AuthorizationError


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state_value(candidate: object) -> object:
    actual = _member(candidate, "state")
    return getattr(actual, "value", actual)


def _findings(
    request: EvaluateProteinRnaDiscordanceSubgroupEquityRequest,
) -> tuple[SubgroupFinding, ...]:
    findings: list[SubgroupFinding] = []
    if any(
        item.status in {CoverageStatus.UNSUPPORTED, CoverageStatus.NOT_EVALUABLE}
        for item in request.coverage
    ) or any(
        item.coverage_status in {CoverageStatus.UNSUPPORTED, CoverageStatus.NOT_EVALUABLE}
        for item in request.performance
    ):
        findings.append(
            SubgroupFinding(
                finding_id="m2205.finding.coverage",
                code=SubgroupFindingCode.COVERAGE_LIMITED,
                message="one or more subgroup records are unsupported or not evaluable",
                evidence=_evidence(request),
            )
        )
    equity_failures = tuple(
        item for item in request.performance if item.equity_status is not EquityStatus.WITHIN_FLOOR
    )
    if equity_failures:
        findings.append(
            SubgroupFinding(
                finding_id="m2205.finding.equity",
                code=SubgroupFindingCode.SAFETY_FLOOR_BREACH,
                message=(
                    f"{len(equity_failures)} subgroup performance records do not have "
                    "within_floor equity status."
                ),
                evidence=_evidence(request),
            )
        )
    calibration_failures = tuple(
        item for item in request.calibration if item.status is not EvaluationStatus.EVALUATED
    )
    if calibration_failures:
        findings.append(
            SubgroupFinding(
                finding_id="m2205.finding.calibration",
                code=SubgroupFindingCode.CALIBRATION_FAILURE,
                message=(
                    f"{len(calibration_failures)} calibration summaries are not evaluated."
                ),
                evidence=_evidence(request),
            )
        )
    return tuple(findings)


def _abstention_reason(findings: tuple[SubgroupFinding, ...]) -> str | None:
    if not findings:
        return None
    return "; ".join(finding.message for finding in findings)


def _support() -> SupportDecision:
    return SupportDecision(
        status=SupportStatus.SUPPORTED,
        reason_code="subgroup_evaluation_completed",
        rationale=(
            "Caller-declared subgroup performance, calibration, coverage, and equity material "
            "satisfies the provisional M22-05 boundary."
        ),
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=(
                f"M22-05 does not estimate {dimension} uncertainty from caller-declared inputs."
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
            "Subgroup evidence is caller-declared and does not establish biological uncertainty.",
        ),
    )


def _evidence(
    request: EvaluateProteinRnaDiscordanceSubgroupEquityRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim=(
                "Caller-declared M22-05 subgroup evidence; issuer authority is not authenticated."
            ),
        )
        for artifact in request.source_artifacts
    )


def _provenance(
    request: EvaluateProteinRnaDiscordanceSubgroupEquityRequest,
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
        activity_id="m2205.activity." + request_digest.removeprefix("sha256:"),
        actor_id=request.context.actor_id,
        module_id=M2205_MODULE_ID,
        module_version=M2205_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request.upstream_result.digest,
            *tuple(artifact.digest for artifact in request.source_artifacts),
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
    "M2205AuthorizationError",
    "M2205EquityEngine",
    "M2205ReplayError",
    "evaluate_protein_rna_discordance_subgroup_equity",
    "preflight_m2205_authorization",
]
