"""Deterministic, fail-closed M16-07 downstream export runtime."""

from __future__ import annotations

# ruff: noqa: C901, TRY003, TRY301
from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m16_07 import (
    M1607_OPERATION,
    CompatibilityReport,
    CompatibilityStatus,
    ExportFinding,
    ExportFindingCode,
    ExportProteinRnaDiscordanceDownstreamContractRequest,
    ExportStatus,
    FieldSupportStatus,
    ProteinRnaDiscordanceDownstreamExportResult,
    SignedDownstreamContract,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m16_07.canonical import result_payload_digest
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    EvidenceReference,
    Limitation,
    SupportDecision,
    SupportStatus,
)

_REQUEST_ADAPTER = TypeAdapter(ExportProteinRnaDiscordanceDownstreamContractRequest)
_RESULT_ADAPTER = TypeAdapter(ProteinRnaDiscordanceDownstreamExportResult)
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
    "missing",
)
_REVIEW_TOKENS: Final = ("warning", "conflict", "discrepancy")


class M1607AuthorizationError(ValueError):
    """Raised when upstream controls do not authorize downstream export."""


class M1607InferenceError(ValueError):
    """Raised when a typed export request cannot be evaluated safely."""


class M1607ReplayVerificationError(ValueError):
    """Raised when an export result digest or replay does not match."""


def _state(value: object) -> str:
    if not isinstance(value, Mapping):
        raise M1607AuthorizationError("M16-07 controls are unavailable")
    state = value.get("state")
    if not isinstance(state, str):
        raise M1607AuthorizationError("M16-07 controls are unavailable")
    return state


def preflight_export_authorization(request: object) -> None:
    """Check seven upstream controls without traversing opaque objects."""

    try:
        if isinstance(request, ExportProteinRnaDiscordanceDownstreamContractRequest):
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
                raise M1607AuthorizationError("M16-07 controls do not authorize export")
            return
        if not isinstance(request, Mapping):
            raise M1607AuthorizationError("M16-07 request controls are unavailable")
        context = request.get("context")
        if not isinstance(context, Mapping):
            raise M1607AuthorizationError("M16-07 request controls are unavailable")
        raw_references = context.get("references")
        if not isinstance(raw_references, Mapping):
            raise M1607AuthorizationError("M16-07 request controls are unavailable")
        for role, expected in _EXPECTED_STATES.items():
            if _state(raw_references.get(role)) != expected:
                raise M1607AuthorizationError("M16-07 controls do not authorize export")
    except M1607AuthorizationError:
        raise
    except Exception as error:
        raise M1607AuthorizationError("M16-07 controls are unavailable") from error


def _evidence(
    request: ExportProteinRnaDiscordanceDownstreamContractRequest,
) -> tuple[EvidenceReference, ...]:
    references = request.context.references
    artifacts: list[ArtifactReference] = [
        request.intended_use_result,
        request.policy.configuration.signature_reference,
        *request.source_artifacts,
        *(item.source_artifact for item in request.fields),
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
            claim="Caller-declared M16-07 downstream export evidence.",
        )
        for artifact in unique.values()
    )


def _declared(request: ExportProteinRnaDiscordanceDownstreamContractRequest) -> str:
    values = [
        request.intended_use_result.artifact_id,
        request.policy.consumer_id,
        request.policy.allowed_owner,
        request.policy.required_media_type,
        request.policy.configuration.configuration_id,
    ]
    values.extend(item.field_id for item in request.fields)
    values.extend(item.name for item in request.fields)
    return " ".join(values).casefold()


def _compatibility(
    request: ExportProteinRnaDiscordanceDownstreamContractRequest,
    declared: str,
    evidence: tuple[EvidenceReference, ...],
) -> tuple[CompatibilityReport, tuple[ExportFindingCode, ...], bool, bool]:
    reasons: list[str] = []
    finding_codes: list[ExportFindingCode] = []
    hard_failure = False
    review_required = any(token in declared for token in _REVIEW_TOKENS)
    allowed_owner = request.policy.allowed_owner
    required_media_type = request.policy.required_media_type
    accepted_ids: list[str] = []
    for field in request.fields:
        if field.owner != allowed_owner:
            reasons.append(f"field {field.field_id} owner is outside the export policy")
            hard_failure = True
            if ExportFindingCode.OWNERSHIP_MISMATCH not in finding_codes:
                finding_codes.append(ExportFindingCode.OWNERSHIP_MISMATCH)
        if field.source_artifact.media_type != required_media_type:
            reasons.append(f"field {field.field_id} media type is incompatible")
            hard_failure = True
            if ExportFindingCode.COMPATIBILITY_FAILED not in finding_codes:
                finding_codes.append(ExportFindingCode.COMPATIBILITY_FAILED)
        if field.support_status is not FieldSupportStatus.SUPPORTED:
            reasons.append(f"field {field.field_id} lacks supported export status")
            hard_failure = True
            if ExportFindingCode.SUPPORT_MISSING not in finding_codes:
                finding_codes.append(ExportFindingCode.SUPPORT_MISSING)
        else:
            accepted_ids.append(field.field_id)
    if review_required:
        reasons.append("caller-declared review marker requires human compatibility review")
        if ExportFindingCode.COMPATIBILITY_FAILED not in finding_codes:
            finding_codes.append(ExportFindingCode.COMPATIBILITY_FAILED)
    if not reasons:
        reasons.append("all fields satisfy ownership, media, support, and compatibility policy")
    status = (
        CompatibilityStatus.INCOMPATIBLE
        if hard_failure
        else CompatibilityStatus.REVIEW_REQUIRED
        if review_required
        else CompatibilityStatus.COMPATIBLE
    )
    return (
        CompatibilityReport(
            report_id="compatibility.downstream.export",
            version="1.0.0",
            status=status,
            consumer_id=request.policy.consumer_id,
            accepted_field_ids=tuple(accepted_ids)
            if status is CompatibilityStatus.COMPATIBLE
            else (),
            reasons=tuple(reasons),
            evidence=evidence[:1],
        ),
        tuple(finding_codes),
        hard_failure,
        review_required,
    )


def _limitations(*, supported: bool) -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="m1607_no_kinase_or_treatment",
            statement="The downstream contract does not infer kinase state or recommend treatment.",
        ),
        Limitation(
            code="m1607_immutable_signed",
            statement="Signed exports are immutable caller-declared compatibility artifacts.",
        ),
        Limitation(
            code="m1607_supported" if supported else "m1607_review_required",
            statement=(
                "All requested fields satisfy the explicit export policy."
                if supported
                else "Unsupported, incompatible, or review-marked fields require safe abstention."
            ),
        ),
    )


class M1607ExportEngine:
    """Stateless deterministic downstream export evaluator."""

    def export(self, request: object) -> ProteinRnaDiscordanceDownstreamExportResult:
        preflight_export_authorization(request)
        try:
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        except Exception as error:
            raise M1607InferenceError from error
        request_digest = sha256_digest(typed.model_dump(mode="json"))
        evidence = _evidence(typed)
        declared = _declared(typed)
        prohibited = any(token in declared for token in _PROHIBITED_TOKENS)
        not_evaluable = any(token in declared for token in _ABSTENTION_TOKENS)
        compatibility, compatibility_findings, hard_failure, review_required = _compatibility(
            typed, declared, evidence
        )
        if prohibited or not_evaluable:
            compatibility = compatibility.model_copy(
                update={
                    "status": CompatibilityStatus.INCOMPATIBLE,
                    "accepted_field_ids": (),
                    "reasons": (
                        *compatibility.reasons,
                        "export boundary marker prevents downstream promotion",
                    ),
                }
            )
        supported = (
            not prohibited and not not_evaluable and not hard_failure and not review_required
        )
        status = ExportStatus.SIGNED if supported else ExportStatus.ABSTAINED
        signed_contract = (
            SignedDownstreamContract(
                contract_id="contract.downstream.export",
                version="1.0.0",
                consumer_id=typed.policy.consumer_id,
                fields=typed.fields,
                ownership=(typed.policy.allowed_owner,),
                compatibility=compatibility,
                signature=typed.policy.configuration.signature_reference,
                signature_algorithm="sha256-caller-declared",
                evidence=evidence,
            )
            if supported
            else None
        )
        findings: list[ExportFinding] = [
            ExportFinding(
                finding_id="finding.provisional-abi",
                code=ExportFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                message="The M16-07 downstream export ABI remains provisional.",
                evidence=evidence[:1],
            )
        ]
        if prohibited:
            findings.append(
                ExportFinding(
                    finding_id="finding.ownership",
                    code=ExportFindingCode.OWNERSHIP_MISMATCH,
                    message="Prohibited ownership or treatment scope was requested.",
                    evidence=evidence[:1],
                )
            )
        elif not_evaluable:
            findings.append(
                ExportFinding(
                    finding_id="finding.support",
                    code=ExportFindingCode.SUPPORT_MISSING,
                    message="Export support is missing or not safely evaluable.",
                    evidence=evidence[:1],
                )
            )
        for code in compatibility_findings:
            if code not in {item.code for item in findings}:
                findings.append(
                    ExportFinding(
                        finding_id=f"finding.{code.value}",
                        code=code,
                        message="Export compatibility policy blocked promotion.",
                        evidence=evidence[:1],
                    )
                )
        support_status = (
            SupportStatus.SUPPORTED
            if supported
            else SupportStatus.REVIEW_REQUIRED
            if review_required
            else SupportStatus.UNSUPPORTED
        )
        payload: dict[str, Any] = {
            "result_id": f"result.{request_digest.removeprefix('sha256:')}",
            "request_digest": request_digest,
            "result_digest": sha256_digest("placeholder"),
            "request": typed,
            "status": status,
            "downstream_contract": signed_contract,
            "compatibility_report": compatibility,
            "findings": tuple(findings),
            "abstention_reason": None
            if supported
            else "Downstream export is not safely promotable.",
            "support_decision": SupportDecision(
                status=support_status,
                reason_code="m1607_supported" if supported else "m1607_review_required",
                rationale=(
                    "Versioned immutable export fields satisfy the consumer policy."
                    if supported
                    else "Ownership, compatibility, support, or boundary review blocked export."
                ),
            ),
            "uncertainty": expected_uncertainty(supported=supported),
            "provenance": expected_provenance(typed, request_digest),
            "evidence": evidence,
            "limitations": _limitations(supported=supported),
            "human_review_required": not supported,
        }
        constructed = ProteinRnaDiscordanceDownstreamExportResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(constructed)
        try:
            return _RESULT_ADAPTER.validate_python(payload, strict=True)
        except Exception as error:
            raise M1607InferenceError from error

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinRnaDiscordanceDownstreamExportResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1607ReplayVerificationError from error
        try:
            validated = _RESULT_ADAPTER.validate_python(
                validated.model_dump(mode="python", warnings=False), strict=True
            )
        except Exception as error:
            raise M1607ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1607ReplayVerificationError
        if replay:
            try:
                expected = self.export(validated.request)
            except Exception as error:
                raise M1607ReplayVerificationError from error
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1607ReplayVerificationError
        return validated


def export_protein_rna_discordance_downstream_contract(
    request: object,
) -> ProteinRnaDiscordanceDownstreamExportResult:
    """Public provisional M16-07 operation."""

    return M1607ExportEngine().export(request)


__all__ = [
    "M1607_OPERATION",
    "M1607AuthorizationError",
    "M1607ExportEngine",
    "M1607InferenceError",
    "M1607ReplayVerificationError",
    "export_protein_rna_discordance_downstream_contract",
    "preflight_export_authorization",
]
