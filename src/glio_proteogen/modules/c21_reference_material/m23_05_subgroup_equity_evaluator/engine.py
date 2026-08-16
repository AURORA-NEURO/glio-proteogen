"""Deterministic, caller-declared M23-05 subgroup equity evaluation runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m23_05 import (
    M2305_CONTRACT_VERSION,
    M2305_MODULE_ID,
    CoverageStatus,
    EquityStatus,
    EvaluateVariantPeptideSubgroupEquityRequest,
    EvaluationStatus,
    SubgroupEvaluationReport,
    SubgroupFinding,
    SubgroupFindingCode,
    VariantPeptideSubgroupEvaluationResult,
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

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateVariantPeptideSubgroupEquityRequest)
_AUTHORIZATION_MESSAGE: Final = (
    "M23-05 subgroup evaluation requires accepted configuration, resolved identity, granted "
    "consent, accepted provenance/quality/support/intended-use controls"
)
_LIMITATIONS: Final = (
    Limitation(
        code="caller_declared_upstream",
        statement=(
            "The M23-04 media boundary is caller-declared; issuer authority and scientific "
            "source content are not authenticated or traversed."
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
            "Kinase ownership, generic all-omics fusion, treatment recommendation, identity "
            "inference, and unsupported-to-negative conversion are outside this module."
        ),
    ),
)


class M2305AuthorizationError(ValueError):
    """Raised when caller-declared controls do not authorize evaluation."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class M2305ReplayError(ValueError):
    """Raised when an evaluation result fails canonical replay verification."""


class M2305EquityEngine:
    """Build and replay one deterministic metadata-only subgroup evaluation."""

    __slots__ = ()

    def generate(self, request: object) -> VariantPeptideSubgroupEvaluationResult:
        preflight_m2305_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        canonical = _REQUEST_ADAPTER.validate_json(
            canonical_json_bytes(validated.model_dump(mode="json")), strict=True
        )
        request_digest = canonical_request_digest(canonical)
        report = SubgroupEvaluationReport(
            report_id="m2305.report." + request_digest.removeprefix("sha256:"),
            version=canonical.configuration.version,
            performance=canonical.performance,
            calibration=canonical.calibration,
            coverage=canonical.coverage,
            configuration=canonical.configuration,
            evidence=_evidence(canonical),
        )
        unsupported = _unsupported_reason(canonical)
        if unsupported is None:
            status = EvaluationStatus.EVALUATED
            output_report: SubgroupEvaluationReport | None = report
            findings: tuple[SubgroupFinding, ...] = ()
            abstention_reason: str | None = None
            support = _support()
            human_review_required = False
        else:
            status = EvaluationStatus.ABSTAINED
            output_report = None
            findings = (
                SubgroupFinding(
                    finding_id="m2305.finding.support",
                    code=SubgroupFindingCode.COVERAGE_LIMITED,
                    message=unsupported,
                    evidence=_evidence(canonical),
                ),
            )
            abstention_reason = unsupported
            support = SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="subgroup_equity_not_evaluable",
                rationale=unsupported,
            )
            human_review_required = True
        payload: dict[str, Any] = {
            "output_type": "variant_peptide_subgroup_evaluation",
            "result_id": result_identifier(canonical),
            "result_version": M2305_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": "sha256:" + ("0" * 64),
            "request": canonical,
            "status": status,
            "report": output_report,
            "findings": findings,
            "abstention_reason": abstention_reason,
            "parent_target": "variant peptide",
            "emits_parent": False,
            "support_decision": support,
            "uncertainty": _uncertainty(),
            "provenance": _provenance(canonical, request_digest),
            "evidence": _evidence(canonical),
            "limitations": _LIMITATIONS,
            "human_review_required": human_review_required,
        }
        provisional = VariantPeptideSubgroupEvaluationResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(provisional)
        return VariantPeptideSubgroupEvaluationResult.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )

    def replay(
        self,
        result: VariantPeptideSubgroupEvaluationResult,
    ) -> VariantPeptideSubgroupEvaluationResult:
        if result.request_digest != canonical_request_digest(result.request):
            raise M2305ReplayError("M23-05 result request digest mismatch")  # noqa: TRY003
        if result.result_id != result_identifier(result.request):
            raise M2305ReplayError("M23-05 result identifier mismatch")  # noqa: TRY003
        if result.result_digest != result_payload_digest(result):
            raise M2305ReplayError("M23-05 result payload digest mismatch")  # noqa: TRY003
        return VariantPeptideSubgroupEvaluationResult.model_validate_json(
            canonical_json_bytes(result), strict=True
        )


def evaluate_variant_peptide_subgroup_equity(
    request: object,
) -> VariantPeptideSubgroupEvaluationResult:
    """Public stateless M23-05 evaluation entry point."""

    return M2305EquityEngine().generate(request)


def preflight_m2305_authorization(candidate: object) -> None:
    """Reject denied controls before reading subgroup material."""

    try:
        context = (
            candidate.context
            if isinstance(candidate, EvaluateVariantPeptideSubgroupEquityRequest)
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
        raise M2305AuthorizationError from None
    if not authorized:
        raise M2305AuthorizationError


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state_value(candidate: object) -> object:
    actual = _member(candidate, "state")
    return getattr(actual, "value", actual)


def _unsupported_reason(
    request: EvaluateVariantPeptideSubgroupEquityRequest,
) -> str | None:
    if any(
        item.status in {CoverageStatus.UNSUPPORTED, CoverageStatus.NOT_EVALUABLE}
        for item in request.coverage
    ):
        return "one or more subgroup coverage summaries are unsupported or not evaluable"
    if any(
        item.coverage_status in {CoverageStatus.UNSUPPORTED, CoverageStatus.NOT_EVALUABLE}
        for item in request.performance
    ):
        return "one or more subgroup performance records lack supported coverage"
    if any(
        item.equity_status in {EquityStatus.RESTRICTED, EquityStatus.NOT_EVALUABLE}
        for item in request.performance
    ):
        return "one or more subgroup equity records are restricted or not evaluable"
    if any(item.status is EvaluationStatus.ABSTAINED for item in request.calibration):
        return "one or more subgroup calibration summaries are not evaluable"
    return None


def _support() -> SupportDecision:
    return SupportDecision(
        status=SupportStatus.SUPPORTED,
        reason_code="subgroup_evaluation_completed",
        rationale=(
            "Caller-declared subgroup performance, calibration, coverage, and equity material "
            "satisfies the provisional M23-05 boundary."
        ),
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=(
                f"M23-05 does not estimate {dimension} uncertainty from caller-declared inputs."
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
    request: EvaluateVariantPeptideSubgroupEquityRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim=(
                "Caller-declared M23-05 subgroup evidence; issuer authority is not authenticated."
            ),
        )
        for artifact in request.source_artifacts
    )


def _provenance(
    request: EvaluateVariantPeptideSubgroupEquityRequest,
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
        activity_id="m2305.activity." + request_digest.removeprefix("sha256:"),
        actor_id=request.context.actor_id,
        module_id=M2305_MODULE_ID,
        module_version=M2305_CONTRACT_VERSION,
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
    "M2305AuthorizationError",
    "M2305EquityEngine",
    "M2305ReplayError",
    "evaluate_variant_peptide_subgroup_equity",
    "preflight_m2305_authorization",
]
