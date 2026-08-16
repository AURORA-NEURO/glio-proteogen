"""Deterministic, fail-closed M16-02 alignment reconciliation runtime."""

from __future__ import annotations

# ruff: noqa: E501, TRY003, TRY301
from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m16_02 import (
    M1602_OPERATION,
    AlignedEvidenceBundle,
    AlignmentDecisionStatus,
    AlignmentDiagnostic,
    AlignmentDimension,
    AlignmentFindingCode,
    AlignmentLink,
    AlignmentLinkStatus,
    DiscrepancyRecord,
    DiscrepancyResolutionStatus,
    DiscrepancySeverity,
    ProteinRnaDiscordanceAlignmentResult,
    ReconcileCrossSourceAlignmentRequest,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m16_02.canonical import result_payload_digest
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    EvidenceReference,
    Limitation,
    SupportDecision,
    SupportStatus,
)

_REQUEST_ADAPTER = TypeAdapter(ReconcileCrossSourceAlignmentRequest)
_RESULT_ADAPTER = TypeAdapter(ProteinRnaDiscordanceAlignmentResult)
_EXPECTED_STATES: Final = {
    "approved_configuration": "accepted",
    "identity_lineage": "resolved",
    "provenance": "accepted",
    "consent": "granted",
    "quality": "accepted",
    "support": "accepted",
    "intended_use": "accepted",
}
_PROHIBITED_TOKENS: Final = (
    "kinase",
    "treatment",
    "identity",
    "consent",
    "all-omics",
    "mutation",
    "relabel",
    "erasure",
)
_ABSTENTION_TOKENS: Final = (
    "unsupported",
    "unknown",
    "not_evaluable",
    "not evaluable",
    "ood",
    "out_of_domain",
    "abstain",
)


class M1602AuthorizationError(ValueError):
    """Raised when upstream controls do not authorize alignment."""


class M1602InferenceError(ValueError):
    """Raised when a typed alignment request cannot be evaluated safely."""


class M1602ReplayVerificationError(ValueError):
    """Raised when a result digest or deterministic replay does not match."""


def _state(value: object) -> str:
    if not isinstance(value, Mapping):
        raise M1602AuthorizationError("M16-02 controls are unavailable")
    state = value.get("state")
    if not isinstance(state, str):
        raise M1602AuthorizationError("M16-02 controls are unavailable")
    return state


def preflight_alignment_authorization(request: object) -> None:
    """Check seven upstream controls without traversing arbitrary opaque objects."""

    try:
        if isinstance(request, ReconcileCrossSourceAlignmentRequest):
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
                raise M1602AuthorizationError("M16-02 controls do not authorize alignment")
            return
        if not isinstance(request, Mapping):
            raise M1602AuthorizationError("M16-02 request controls are unavailable")
        context = request.get("context")
        if not isinstance(context, Mapping):
            raise M1602AuthorizationError("M16-02 request controls are unavailable")
        raw_references = context.get("references")
        if not isinstance(raw_references, Mapping):
            raise M1602AuthorizationError("M16-02 request controls are unavailable")
        for role, expected in _EXPECTED_STATES.items():
            if _state(raw_references.get(role)) != expected:
                raise M1602AuthorizationError("M16-02 controls do not authorize alignment")
    except M1602AuthorizationError:
        raise
    except Exception as error:
        raise M1602AuthorizationError("M16-02 controls are unavailable") from error


def _evidence(request: ReconcileCrossSourceAlignmentRequest) -> tuple[EvidenceReference, ...]:
    references = request.context.references
    artifacts: list[ArtifactReference] = [
        request.upstream_result,
        request.configuration.reference_artifact,
        *request.source_artifacts,
    ]
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
    unique = {item.digest: item for item in artifacts}
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim="Caller-declared M16-01 alignment and reconciliation evidence.",
        )
        for artifact in unique.values()
    )


def _declared(request: ReconcileCrossSourceAlignmentRequest) -> str:
    values = [
        request.upstream_result.artifact_id,
        request.configuration.configuration_id,
        request.configuration.conflict_policy,
    ]
    values.extend(item.artifact_id for item in request.source_artifacts)
    return " ".join(values).casefold()


def _link_status(declared: str) -> AlignmentLinkStatus:
    if any(token in declared for token in _ABSTENTION_TOKENS):
        return AlignmentLinkStatus.NOT_EVALUABLE
    if any(
        token in declared
        for token in ("critical", "conflict", "discrepancy", "mismatch", "warning")
    ):
        return AlignmentLinkStatus.DISCREPANT
    return AlignmentLinkStatus.ALIGNED


def _link(
    request: ReconcileCrossSourceAlignmentRequest,
    status: AlignmentLinkStatus,
    evidence: tuple[EvidenceReference, ...],
) -> AlignmentLink:
    return AlignmentLink(
        link_id="link.cross-source.primary",
        dimensions=request.configuration.enabled_dimensions,
        source_artifacts=request.source_artifacts,
        canonical_key="sample-1:time-1:territory-1:analyte-1",
        observed_values=("sample-1", "time-1", "territory-1", "analyte-1"),
        status=status,
        evidence=evidence[:1],
    )


def _discrepancy(
    declared: str,
    link: AlignmentLink,
    evidence: tuple[EvidenceReference, ...],
) -> tuple[DiscrepancyRecord, ...]:
    if "resolved" in declared:
        return (
            DiscrepancyRecord(
                discrepancy_id="discrepancy.resolved",
                dimensions=(AlignmentDimension.TIME,),
                source_link_ids=(link.link_id,),
                description="Collection time discrepancy was resolved by the locked reference.",
                severity=DiscrepancySeverity.WARNING,
                resolution_status=DiscrepancyResolutionStatus.RESOLVED,
                resolution="Signed reference selected the canonical collection time.",
                evidence=evidence[:1],
            ),
        )
    if any(token in declared for token in ("critical", "conflict", "discrepancy", "mismatch")):
        return (
            DiscrepancyRecord(
                discrepancy_id="discrepancy.critical",
                dimensions=(AlignmentDimension.TIME, AlignmentDimension.MODALITY),
                source_link_ids=(link.link_id,),
                description="Cross-source time or modality conflict remains unresolved.",
                severity=DiscrepancySeverity.CRITICAL,
                resolution_status=DiscrepancyResolutionStatus.OPEN,
                evidence=evidence[:1],
            ),
        )
    if "warning" in declared:
        return (
            DiscrepancyRecord(
                discrepancy_id="discrepancy.warning",
                dimensions=(AlignmentDimension.TERRITORY,),
                source_link_ids=(link.link_id,),
                description="Territory metadata requires reviewer confirmation.",
                severity=DiscrepancySeverity.WARNING,
                resolution_status=DiscrepancyResolutionStatus.OPEN,
                evidence=evidence[:1],
            ),
        )
    return ()


def _diagnostic(
    status: AlignmentLinkStatus, evidence: tuple[EvidenceReference, ...]
) -> tuple[AlignmentDiagnostic, ...]:
    return (
        AlignmentDiagnostic(
            diagnostic_id="diagnostic.cross-source.primary",
            status=status,
            message=(
                "Cross-source dimensions aligned within the provisional support domain."
                if status is AlignmentLinkStatus.ALIGNED
                else "Cross-source alignment requires review or is not safely evaluable."
            ),
            evidence=evidence[:1],
        ),
    )


def _limitations(*, supported: bool) -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="m1602_no_kinase_or_treatment",
            statement="Alignment reconciliation does not infer kinase activity or recommend treatment.",
        ),
        Limitation(
            code="m1602_provisional_abi",
            statement="The M16-02 ABI and architecture selection remain provisional pending owner review.",
        ),
        Limitation(
            code="m1602_supported" if supported else "m1602_review_required",
            statement=(
                "All configured dimensions reconciled without a critical discrepancy."
                if supported
                else "Unsupported, discrepant, OOD, or incomplete inputs require review."
            ),
        ),
    )


class M1602AlignmentEngine:
    """Stateless deterministic cross-source alignment evaluator."""

    def reconcile(self, request: object) -> ProteinRnaDiscordanceAlignmentResult:
        preflight_alignment_authorization(request)
        try:
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        except Exception as error:
            raise M1602InferenceError from error
        request_digest = sha256_digest(typed.model_dump(mode="json"))
        evidence = _evidence(typed)
        declared = _declared(typed)
        prohibited = any(token in declared for token in _PROHIBITED_TOKENS)
        status = _link_status(declared)
        link = _link(typed, status, evidence)
        discrepancies = _discrepancy(declared, link, evidence)
        critical_open = any(
            item.severity is DiscrepancySeverity.CRITICAL
            and item.resolution_status is not DiscrepancyResolutionStatus.RESOLVED
            for item in discrepancies
        )
        not_evaluable = status is AlignmentLinkStatus.NOT_EVALUABLE
        open_discrepancy = any(
            item.resolution_status is not DiscrepancyResolutionStatus.RESOLVED
            for item in discrepancies
        )
        supported = (
            not prohibited and not not_evaluable and not critical_open and not open_discrepancy
        )
        review_required = not supported and not prohibited and not not_evaluable
        bundle = (
            None
            if prohibited or not_evaluable
            else AlignedEvidenceBundle(
                bundle_id="bundle.cross-source.primary",
                version="1.0.0",
                links=(link,),
                discrepancies=discrepancies,
                configuration=typed.configuration,
                evidence=evidence[:1],
            )
        )
        findings: list[AlignmentFindingCode] = [
            AlignmentFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
        ]
        if prohibited:
            findings.append(AlignmentFindingCode.UPSTREAM_UNSUPPORTED)
        elif not_evaluable:
            findings.append(AlignmentFindingCode.INPUT_INCOMPLETE)
        elif critical_open:
            findings.append(AlignmentFindingCode.CRITICAL_CONFLICT)
        elif discrepancies:
            findings.append(AlignmentFindingCode.DISCREPANCY_OPEN)
        if any("reference" in token for token in declared.split()):
            findings.append(AlignmentFindingCode.REFERENCE_MISMATCH)
        unique_findings = tuple(dict.fromkeys(findings))
        decision = (
            AlignmentDecisionStatus.ABSTAINED
            if prohibited or not_evaluable
            else AlignmentDecisionStatus.RECONCILED
            if supported
            else AlignmentDecisionStatus.REVIEW_REQUIRED
        )
        payload: dict[str, Any] = {
            "result_id": f"result.{request_digest.removeprefix('sha256:')}",
            "request_digest": request_digest,
            "result_digest": sha256_digest("placeholder"),
            "request": typed,
            "status": decision,
            "bundle": bundle,
            "diagnostics": _diagnostic(status, evidence),
            "findings": unique_findings,
            "abstention_reason": None
            if supported or review_required
            else "Alignment inputs are not safely evaluable.",
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED
                if supported
                else SupportStatus.REVIEW_REQUIRED
                if review_required
                else SupportStatus.UNSUPPORTED,
                reason_code="m1602_supported" if supported else "m1602_review_required",
                rationale=(
                    "All configured source dimensions reconciled without critical conflict."
                    if supported
                    else "Alignment promotion is blocked pending discrepancy, support, or input review."
                ),
            ),
            "uncertainty": expected_uncertainty(supported=supported),
            "provenance": expected_provenance(typed, request_digest),
            "evidence": evidence,
            "limitations": _limitations(supported=supported),
            "human_review_required": not supported,
        }
        constructed = ProteinRnaDiscordanceAlignmentResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(constructed)
        try:
            return _RESULT_ADAPTER.validate_python(payload, strict=True)
        except Exception as error:
            raise M1602InferenceError from error

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinRnaDiscordanceAlignmentResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1602ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1602ReplayVerificationError
        if replay:
            try:
                expected = self.reconcile(validated.request)
            except Exception as error:
                raise M1602ReplayVerificationError from error
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1602ReplayVerificationError
        return validated


def reconcile_cross_source_alignment(
    request: object,
) -> ProteinRnaDiscordanceAlignmentResult:
    """Public provisional M16-02 operation."""

    return M1602AlignmentEngine().reconcile(request)


__all__ = [
    "M1602_OPERATION",
    "M1602AlignmentEngine",
    "M1602AuthorizationError",
    "M1602InferenceError",
    "M1602ReplayVerificationError",
    "preflight_alignment_authorization",
    "reconcile_cross_source_alignment",
]
