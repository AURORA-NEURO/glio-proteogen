"""Deterministic, fail-closed M17-02 alignment runtime."""

from __future__ import annotations

# ruff: noqa: TRY003, TRY301
from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m17_02 import (
    M1702_MODULE_ID,
    AlignedEvidenceBundle,
    AlignmentAxis,
    AlignmentFinding,
    AlignmentFindingCode,
    AlignmentResultStatus,
    AlignmentStatus,
    AlignVariantPeptideCrossSourceEvidenceRequest,
    Discrepancy,
    DiscrepancyCode,
    SourceObservation,
    VariantPeptideCrossSourceAlignmentResult,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
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

_REQUEST_ADAPTER = TypeAdapter(AlignVariantPeptideCrossSourceEvidenceRequest)
_RESULT_ADAPTER = TypeAdapter(VariantPeptideCrossSourceAlignmentResult)
_EXPECTED_STATES: Final = {
    "approved_configuration": "accepted",
    "identity_lineage": "resolved",
    "provenance": "accepted",
    "consent": "granted",
    "quality": "accepted",
    "support": "accepted",
    "intended_use": "accepted",
}
_ABSTENTION_TOKENS: Final = (
    "unsupported",
    "unknown",
    "missing",
    "not_evaluable",
    "not evaluable",
    "ood",
    "out_of_domain",
    "abstain",
)
_PROHIBITED_TOKENS: Final = (
    "kinase",
    "treatment",
    "identity_inference",
    "consent_inference",
    "all-omics",
    "all_omics",
    "mutation",
    "relabel",
    "erasure",
)
_AXIS_FIELDS: Final = {
    AlignmentAxis.SAMPLE: "sample_id",
    AlignmentAxis.TIME: "time_key",
    AlignmentAxis.TERRITORY: "territory",
    AlignmentAxis.ANALYTE: "analyte",
    AlignmentAxis.MODALITY: "modality",
    AlignmentAxis.REFERENCE: "reference",
    AlignmentAxis.BIOLOGICAL_CONTEXT: "biological_context",
}
_AXIS_CODES: Final = {
    AlignmentAxis.SAMPLE: DiscrepancyCode.SAMPLE_MISMATCH,
    AlignmentAxis.TIME: DiscrepancyCode.TIME_MISMATCH,
    AlignmentAxis.TERRITORY: DiscrepancyCode.TERRITORY_MISMATCH,
    AlignmentAxis.ANALYTE: DiscrepancyCode.ANALYTE_MISMATCH,
    AlignmentAxis.MODALITY: DiscrepancyCode.MODALITY_MISMATCH,
    AlignmentAxis.REFERENCE: DiscrepancyCode.REFERENCE_MISMATCH,
    AlignmentAxis.BIOLOGICAL_CONTEXT: DiscrepancyCode.BIOLOGICAL_CONTEXT_CONFLICT,
}


class M1702AuthorizationError(ValueError):
    """Raised when upstream controls do not authorize alignment."""


class M1702ExportError(ValueError):
    """Raised when a typed alignment request cannot be evaluated safely."""


class M1702ReplayVerificationError(ValueError):
    """Raised when an alignment result digest or replay does not match."""


def _state(value: object) -> str:
    if not isinstance(value, Mapping):
        raise M1702AuthorizationError("M17-02 controls are unavailable")
    state = value.get("state")
    if not isinstance(state, str):
        raise M1702AuthorizationError("M17-02 controls are unavailable")
    return state


def preflight_alignment_authorization(request: object) -> None:
    """Check all seven caller-declared controls before typed alignment."""

    try:
        if isinstance(request, AlignVariantPeptideCrossSourceEvidenceRequest):
            references = request.context.references
            actual = {
                "approved_configuration": references.approved_configuration.state.value,
                "identity_lineage": references.identity_lineage.state.value,
                "provenance": references.provenance.state.value,
                "consent": references.consent.state.value,
                "quality": references.quality.state.value,
                "support": references.support.state.value,
                "intended_use": references.intended_use.state.value,
            }
            if actual != _EXPECTED_STATES:
                raise M1702AuthorizationError("M17-02 controls do not authorize alignment")
            return
        if not isinstance(request, Mapping):
            raise M1702AuthorizationError("M17-02 request controls are unavailable")
        context = request.get("context")
        if not isinstance(context, Mapping):
            raise M1702AuthorizationError("M17-02 request controls are unavailable")
        raw_references = context.get("references")
        if not isinstance(raw_references, Mapping):
            raise M1702AuthorizationError("M17-02 request controls are unavailable")
        for role, expected in _EXPECTED_STATES.items():
            if _state(raw_references.get(role)) != expected:
                raise M1702AuthorizationError("M17-02 controls do not authorize alignment")
    except M1702AuthorizationError:
        raise
    except Exception as error:
        raise M1702AuthorizationError("M17-02 controls are unavailable") from error


def _evidence(
    request: AlignVariantPeptideCrossSourceEvidenceRequest,
) -> tuple[EvidenceReference, ...]:
    references = request.context.references
    artifacts: list[ArtifactReference] = [*request.source_artifacts]
    artifacts.extend(item.source_artifact for item in request.observations)
    artifacts.extend(
        (
            request.policy.configuration.model_reference,
            references.approved_configuration.evidence,
            references.identity_lineage.evidence,
            references.provenance.evidence,
            references.consent.evidence,
            references.quality.evidence,
            references.support.evidence,
            references.intended_use.evidence,
        )
    )
    unique = {item.digest: item for item in artifacts}
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim="Caller-declared M17-02 alignment and reconciliation evidence.",
        )
        for artifact in unique.values()
    )


def _declared(request: AlignVariantPeptideCrossSourceEvidenceRequest) -> str:
    values = [
        request.request_id,
        request.policy.configuration.configuration_id,
        request.policy.configuration.method,
        *(item.observation_id for item in request.observations),
        *(item.analyte for item in request.observations),
        *(item.biological_context for item in request.observations),
        *(item.source_artifact.artifact_id for item in request.observations),
    ]
    return " ".join(values).casefold()


def _discrepancies(
    observations: tuple[SourceObservation, ...],
) -> tuple[Discrepancy, ...]:
    discrepancies: list[Discrepancy] = []
    for axis, field_name in _AXIS_FIELDS.items():
        values = tuple(str(getattr(item, field_name)) for item in observations)
        if len(set(values)) > 1:
            discrepancies.append(
                Discrepancy(
                    discrepancy_id=f"discrepancy.{axis.value}",
                    code=_AXIS_CODES[axis],
                    axis=axis,
                    observation_ids=tuple(item.observation_id for item in observations),
                    message=f"Cross-source {axis.value} values are not reconciled.",
                )
            )
    if any(item.status is not AlignmentStatus.ALIGNED for item in observations):
        discrepancies.append(
            Discrepancy(
                discrepancy_id="discrepancy.unresolved_alignment",
                code=DiscrepancyCode.UNRESOLVED_ALIGNMENT,
                axis=AlignmentAxis.SAMPLE,
                observation_ids=tuple(item.observation_id for item in observations),
                message="One or more source observations are not aligned.",
            )
        )
    return tuple(discrepancies)


def _uncertainty(*, supported: bool) -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED if supported else EstimateState.NOT_ESTIMABLE,
        probability=0.9 if supported else None,
        rationale=(
            "All seven alignment axes and source controls passed."
            if supported
            else "Alignment, source support, or review constraints were not safely evaluable."
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
            "Cross-source discrepancies are preserved and never converted to negative findings.",
        ),
    )


def _provenance(
    request: AlignVariantPeptideCrossSourceEvidenceRequest,
    request_digest: str,
) -> ProvenanceRecord:
    references = request.context.references
    controls = (
        ControlDecisionRecord(
            role=ControlRole.APPROVED_CONFIGURATION,
            decision_id=references.approved_configuration.decision_id,
            state=references.approved_configuration.state.value,
            policy_version=references.approved_configuration.policy_version,
            evidence_digest=references.approved_configuration.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.IDENTITY_LINEAGE,
            decision_id=references.identity_lineage.decision_id,
            state=references.identity_lineage.state.value,
            policy_version=references.identity_lineage.policy_version,
            evidence_digest=references.identity_lineage.evidence.digest,
            subject_digest=references.identity_lineage.binding_digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.PROVENANCE,
            decision_id=references.provenance.decision_id,
            state=references.provenance.state.value,
            policy_version=references.provenance.policy_version,
            evidence_digest=references.provenance.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.CONSENT,
            decision_id=references.consent.decision_id,
            state=references.consent.state.value,
            policy_version=references.consent.policy_version,
            evidence_digest=references.consent.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.QUALITY,
            decision_id=references.quality.decision_id,
            state=references.quality.state.value,
            policy_version=references.quality.policy_version,
            evidence_digest=references.quality.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.SUPPORT,
            decision_id=references.support.decision_id,
            state=references.support.state.value,
            policy_version=references.support.policy_version,
            evidence_digest=references.support.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.INTENDED_USE,
            decision_id=references.intended_use.decision_id,
            state=references.intended_use.state.value,
            policy_version=references.intended_use.policy_version,
            evidence_digest=references.intended_use.evidence.digest,
        ),
    )
    input_digests = (
        request_digest,
        *(item.source_artifact.digest for item in request.observations),
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M1702_MODULE_ID,
        module_version="0.1.0-provisional",
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=request.policy.configuration.model_reference.digest,
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=controls,
    )


def _limitations(*, supported: bool) -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="m1702_no_kinase_or_treatment",
            statement="Alignment does not infer kinase state or recommend treatment.",
        ),
        Limitation(
            code="m1702_conflicts_preserved",
            statement="Irreconcilable source disagreement remains explicit and reviewable.",
        ),
        Limitation(
            code="m1702_supported" if supported else "m1702_review_required",
            statement=(
                "All required source axes aligned under the locked policy."
                if supported
                else "Unsupported, missing, or conflicting sources require safe abstention."
            ),
        ),
    )


class M1702AlignmentEngine:
    """Stateless deterministic cross-source alignment evaluator."""

    def export(self, request: object) -> VariantPeptideCrossSourceAlignmentResult:
        preflight_alignment_authorization(request)
        try:
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        except Exception as error:
            raise M1702ExportError from error
        request_digest = canonical_request_digest(typed)
        evidence = _evidence(typed)
        declared = _declared(typed)
        boundary = any(token in declared for token in _ABSTENTION_TOKENS + _PROHIBITED_TOKENS)
        discrepancies = _discrepancies(typed.observations)
        supported = not boundary and not discrepancies
        status = AlignmentResultStatus.RECONCILED if supported else AlignmentResultStatus.ABSTAINED
        bundle = (
            AlignedEvidenceBundle(
                bundle_id=f"bundle.{request_digest.removeprefix('sha256:')}",
                version="1.0.0",
                observations=typed.observations,
                discrepancy_map=(),
                alignment_status=AlignmentStatus.ALIGNED,
                evidence=evidence,
            )
            if supported
            else None
        )
        findings = [
            AlignmentFinding(
                finding_id="finding.provisional-abi",
                code=AlignmentFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                message="The M17-02 alignment ABI remains provisional.",
                evidence=evidence[:1],
            )
        ]
        if discrepancies or boundary:
            findings.append(
                AlignmentFinding(
                    finding_id="finding.discrepancy-review",
                    code=AlignmentFindingCode.DISCREPANCY_REQUIRES_REVIEW,
                    message=("Cross-source discrepancy or boundary marker requires human review."),
                    evidence=evidence[:1],
                )
            )
        support_status = (
            SupportStatus.SUPPORTED
            if supported
            else (SupportStatus.UNSUPPORTED if boundary else SupportStatus.REVIEW_REQUIRED)
        )
        payload: dict[str, Any] = {
            "output_type": "variant_peptide_cross_source_alignment",
            "result_id": f"result.{request_digest.removeprefix('sha256:')}",
            "request_digest": request_digest,
            "result_digest": sha256_digest("placeholder"),
            "request": typed,
            "status": status,
            "aligned_bundle": bundle,
            "discrepancy_map": discrepancies,
            "findings": tuple(findings),
            "abstention_reason": None
            if supported
            else "Cross-source alignment is not safely promotable.",
            "support_decision": SupportDecision(
                status=support_status,
                reason_code="m1702_aligned" if supported else "m1702_review_required",
                rationale=(
                    "All seven source axes agree under the locked alignment policy."
                    if supported
                    else "Discrepancy, support, or prohibited-boundary review blocked alignment."
                ),
            ),
            "uncertainty": _uncertainty(supported=supported),
            "provenance": _provenance(typed, request_digest),
            "evidence": evidence,
            "limitations": _limitations(supported=supported),
            "human_review_required": not supported,
        }
        constructed = VariantPeptideCrossSourceAlignmentResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(constructed)
        try:
            return _RESULT_ADAPTER.validate_python(payload, strict=True)
        except Exception as error:
            raise M1702ExportError from error

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> VariantPeptideCrossSourceAlignmentResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1702ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1702ReplayVerificationError
        if replay:
            try:
                expected = self.export(validated.request)
            except Exception as error:
                raise M1702ReplayVerificationError from error
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1702ReplayVerificationError
        return validated


def align_variant_peptide_cross_source_evidence(
    request: object,
) -> VariantPeptideCrossSourceAlignmentResult:
    """Public provisional M17-02 alignment operation."""

    return M1702AlignmentEngine().export(request)


__all__ = [
    "M1702AlignmentEngine",
    "M1702AuthorizationError",
    "M1702ExportError",
    "M1702ReplayVerificationError",
    "align_variant_peptide_cross_source_evidence",
    "preflight_alignment_authorization",
]
