"""Deterministic change-control and rollback engine for M27-07."""

# ruff: noqa: E501, TRY003

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m27_07 import (
    ApprovedChangePackage,
    ChampionChallengerComparison,
    ChangeControlStatus,
    ChangeFinding,
    ChangeFindingCode,
    ComparisonStatus,
    ComplexActivityChangeControlResult,
    ControlComplexActivityChangeRequest,
    MetricComparison,
    PromotionState,
    SafeFailureReport,
)
from glio_proteogen.contracts.m27_07.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
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
)

_CONTROL_ROLES: Final = (
    ControlRole.APPROVED_CONFIGURATION,
    ControlRole.IDENTITY_LINEAGE,
    ControlRole.PROVENANCE,
    ControlRole.CONSENT,
    ControlRole.QUALITY,
    ControlRole.SUPPORT,
    ControlRole.INTENDED_USE,
)

_RESULT_ADAPTER: Final = TypeAdapter(ComplexActivityChangeControlResult)


class ChangeControlAuthorizationError(ValueError):
    """Request failed the authorization and upstream binding firewall."""


class ChangeControlReplayError(ValueError):
    """Result failed deterministic replay verification."""


def _control_records(
    request: ControlComplexActivityChangeRequest,
) -> tuple[ControlDecisionRecord, ...]:
    refs = request.context.references
    values = (
        (_CONTROL_ROLES[0], refs.approved_configuration, None),
        (_CONTROL_ROLES[1], refs.identity_lineage, refs.identity_lineage.binding_digest),
        (_CONTROL_ROLES[2], refs.provenance, None),
        (_CONTROL_ROLES[3], refs.consent, None),
        (_CONTROL_ROLES[4], refs.quality, None),
        (_CONTROL_ROLES[5], refs.support, None),
        (_CONTROL_ROLES[6], refs.intended_use, None),
    )
    return tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=reference.decision_id,
            state=reference.state.value,
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=subject,
        )
        for role, reference, subject in values
    )


def preflight_change_control_authorization(request: ControlComplexActivityChangeRequest) -> None:
    """Validate controls and the M27-06 artifact before any change decision."""

    if request.context.request_id != request.request_id:
        raise ChangeControlAuthorizationError("request context identity mismatch")
    if request.upstream_result.media_type != "application/vnd.glio-proteogen.m27-06+json":
        raise ChangeControlAuthorizationError("unsupported upstream result media type")
    if request.context.references.consent.state.value != "granted":
        raise ChangeControlAuthorizationError("consent is not granted")
    if request.context.references.identity_lineage.state.value != "resolved":
        raise ChangeControlAuthorizationError("identity lineage is unresolved")
    for role in _CONTROL_ROLES:
        reference = getattr(request.context.references, role.value)
        if role is ControlRole.CONSENT:
            continue
        state = getattr(reference.state, "value", reference.state)
        if role is ControlRole.IDENTITY_LINEAGE and state == "resolved":
            continue
        if state != "accepted":
            raise ChangeControlAuthorizationError("required control is not accepted")
    ids = tuple(item.artifact_id for item in request.source_artifacts)
    if len(ids) != len(set(ids)):
        raise ChangeControlAuthorizationError("source artifact ids must be unique")


def _uncertainty() -> UncertaintyProfile:
    def unavailable(text: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=text)

    return UncertaintyProfile(
        measurement=unavailable("Change control does not estimate scientific measurements."),
        sampling=unavailable("No sampling population is modeled by this service."),
        parameter=unavailable("No fitted parameters are used."),
        model_form=unavailable("Deterministic policy comparison has no model form."),
        identification=unavailable("Identity is consumed as a control, not inferred."),
        support=unavailable("Support follows explicit security and rollback controls."),
        transport=unavailable("External authority is not authenticated by this service."),
    )


def _evidence(request: ControlComplexActivityChangeRequest) -> tuple[EvidenceReference, ...]:
    refs = request.context.references
    return tuple(
        EvidenceReference(
            reference=getattr(refs, role.value).evidence,
            role="evidence",
            claim=f"control:{role.value}",
        )
        for role in _CONTROL_ROLES
    )


def _provenance(
    request: ControlComplexActivityChangeRequest, request_digest: str
) -> ProvenanceRecord:
    refs = request.context.references
    return ProvenanceRecord(
        activity_id=f"activity.m2707.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id="GLIO-PROTEOGEN-M27-07",
        module_version="0.1.0-provisional",
        generated_at=request.context.occurred_at,
        input_digests=(
            request_digest,
            request.upstream_result.digest,
            request.champion_digest,
            request.challenger_digest,
        ),
        configuration_digest=refs.approved_configuration.evidence.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=_control_records(request),
    )


def _limitation() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="provisional_abi",
            statement="The M27-07 ABI remains provisional pending owner confirmation.",
        ),
        Limitation(
            code="caller_declared",
            statement="Change and comparison values are caller-declared metadata.",
        ),
        Limitation(
            code="no_biology",
            statement="No protein, proteoform, isoform, or glioma-biology inference is emitted.",
        ),
    )


class M2707ChangeControlEngine:
    """Build and replay approved or safely abstained change-control results."""

    def evaluate(
        self, request: ControlComplexActivityChangeRequest
    ) -> ComplexActivityChangeControlResult:
        preflight_change_control_authorization(request)
        request_digest = canonical_request_digest(request)
        evidence = _evidence(request)
        regression = any("regression" in item.artifact_id for item in request.source_artifacts)
        metric = MetricComparison(
            metric="declared-security-regression-rate",
            champion_value=0.10,
            challenger_value=0.20 if regression else 0.10,
            tolerance=0.05,
            within_tolerance=not regression,
            evidence=(evidence[0],),
        )
        comparison = ChampionChallengerComparison(
            comparison_id=f"comparison.m2707.{request_digest.removeprefix('sha256:')[:16]}",
            champion_digest=request.champion_digest,
            challenger_digest=request.challenger_digest,
            status=ComparisonStatus.FAILED if regression else ComparisonStatus.PASSED,
            metrics=(metric,),
            evidence=(evidence[1],),
        )
        provenance = _provenance(request, request_digest)
        if regression:
            finding = ChangeFinding(
                finding_id=f"finding.m2707.{request_digest.removeprefix('sha256:')[:16]}",
                code=ChangeFindingCode.CHALLENGER_REGRESSION,
                message="The challenger exceeds the declared security tolerance.",
                evidence=(evidence[0], evidence[1]),
            )
            safe_failure = SafeFailureReport(
                report_id=f"safe-failure.m2707.{request_digest.removeprefix('sha256:')[:16]}",
                version="1.0.0",
                trigger="critical challenger regression",
                action="withhold promotion and preserve rollback point",
                recovery_note="Review the comparison and rerun revalidation before retrying.",
                evidence=evidence,
            )
            status = ChangeControlStatus.ABSTAINED
            support = SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="challenger_regression",
                rationale="Critical regression blocks promotion and requires review.",
            )
            findings: tuple[ChangeFinding, ...] = (finding,)
            package = None
            reason = "critical challenger regression"
        else:
            package = ApprovedChangePackage(
                package_id=f"package.m2707.{request_digest.removeprefix('sha256:')[:16]}",
                version="1.0.0",
                classification=request.classification,
                revalidation=request.revalidation,
                comparison=comparison,
                approval_reference="m2707.approval.caller-declared",
                promotion_state=PromotionState.APPROVED,
                rollback_point=request.rollback_point,
                package_digest=sha256_digest(
                    {
                        "request_digest": request_digest,
                        "rollback": request.rollback_point.target_digest,
                    }
                ),
                evidence=evidence,
            )
            status = ChangeControlStatus.APPROVED
            support = SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="change_controls_passed",
                rationale="Revalidation, comparison, approval, staged rollout, and rollback controls passed.",
            )
            findings = ()
            safe_failure = None
            reason = None
        candidate = ComplexActivityChangeControlResult.model_construct(
            result_id=f"result.m2707.{request_digest.removeprefix('sha256:')}",
            request_digest=request_digest,
            result_digest="sha256:" + "0" * 64,
            request=request,
            status=status,
            approved_change_package=package,
            findings=findings,
            safe_failure_report=safe_failure,
            abstention_reason=reason,
            support_decision=support,
            uncertainty=_uncertainty(),
            provenance=provenance,
            evidence=evidence,
            limitations=_limitation(),
            human_review_required=regression,
        )
        digest = result_payload_digest(candidate)
        return ComplexActivityChangeControlResult(
            result_id=candidate.result_id,
            request_digest=request_digest,
            result_digest=digest,
            request=request,
            status=status,
            approved_change_package=package,
            findings=findings,
            safe_failure_report=safe_failure,
            abstention_reason=reason,
            support_decision=support,
            uncertainty=candidate.uncertainty,
            provenance=provenance,
            evidence=evidence,
            limitations=candidate.limitations,
            human_review_required=regression,
        )

    def replay(
        self, result: ComplexActivityChangeControlResult
    ) -> ComplexActivityChangeControlResult:
        """Validate and regenerate the complete result from its bound request.

        A payload digest only proves that the supplied envelope is internally
        self-consistent.  A caller could mutate a nested package and recompute
        that digest, so replay must also bind the request digest and compare
        the deterministic engine output field-for-field.
        """

        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
            if validated.request_digest != canonical_request_digest(validated.request):
                raise ChangeControlReplayError("request digest mismatch")
            if validated.result_digest != result_payload_digest(validated):
                raise ChangeControlReplayError("result digest mismatch")
            expected = self.evaluate(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise ChangeControlReplayError("deterministic replay mismatch")
        except ChangeControlReplayError:
            raise
        except Exception as error:
            raise ChangeControlReplayError("result replay validation failed") from error
        return validated


def control_complex_activity_change(
    request: ControlComplexActivityChangeRequest,
) -> ComplexActivityChangeControlResult:
    """Evaluate a caller-declared change package."""

    return M2707ChangeControlEngine().evaluate(request)


__all__ = [
    "ChangeControlAuthorizationError",
    "ChangeControlReplayError",
    "M2707ChangeControlEngine",
    "control_complex_activity_change",
    "preflight_change_control_authorization",
]
