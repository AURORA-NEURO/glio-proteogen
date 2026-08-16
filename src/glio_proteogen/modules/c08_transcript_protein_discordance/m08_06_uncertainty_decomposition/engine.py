"""Deterministic, replay-verifiable, safe-abstaining M08-06 engine."""

# Public diagnostics intentionally collapse hostile input into stable errors.
# ruff: noqa: TRY003

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import BaseModel, TypeAdapter

from glio_proteogen.contracts.m08_06 import (
    M0806_CONTRACT_VERSION,
    M0806_EVIDENCE_CLAIM,
    M0806_PARENT,
    DecomposeTranscriptProteinUncertaintyRequest,
    SensitivityEnvelope,
    TranscriptProteinUncertaintyDecompositionResult,
    UncertaintyDecompositionStatus,
    UncertaintyFinding,
    UncertaintyFindingCode,
    canonical_request_digest,
    expected_provenance,
    expected_uncertainty,
    result_payload_digest,
    verify_result_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    EvidenceReference,
    Limitation,
    SupportDecision,
    SupportStatus,
)

from .kernel import M0806UncertaintyKernel

_REQUEST_ADAPTER: Final = TypeAdapter(DecomposeTranscriptProteinUncertaintyRequest)
_RESULT_ADAPTER: Final = TypeAdapter(TranscriptProteinUncertaintyDecompositionResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class M0806AuthorizationError(PermissionError):
    """Required identity, consent, provenance, and support controls are not accepted."""

    def __init__(self) -> None:
        super().__init__(
            "M08-06 requires accepted configuration, resolved identity, accepted provenance "
            "and quality/support/intended-use controls with granted consent"
        )


class M0806ReplayVerificationError(ValueError):
    """A result is not a canonical receipt for its exact request."""

    def __init__(self, detail: str) -> None:
        super().__init__(f"M08-06 replay verification failed: {detail}")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m0806_authorization(candidate: object) -> None:
    """Check all seven controls before validating the complete upstream handoff."""

    try:
        context = _member(candidate, "context")
        refs = _member(context, "references")
        expected = {
            "approved_configuration": "accepted",
            "identity_lineage": "resolved",
            "provenance": "accepted",
            "consent": "granted",
            "quality": "accepted",
            "support": "accepted",
            "intended_use": "accepted",
        }
        states = {role: _state(_member(_member(refs, role), "state")) for role in expected}
    except Exception:  # noqa: BLE001 - hostile objects fail closed.
        raise M0806AuthorizationError from None
    if states != expected:
        raise M0806AuthorizationError


def _evidence(
    request: DecomposeTranscriptProteinUncertaintyRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M0806_EVIDENCE_CLAIM)
        for artifact in request.source_artifacts
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="uncertainty_decomposition_only",
            statement="Output is limited to typed uncertainty dimensions and sensitivity metadata.",
        ),
        Limitation(
            code="no_kinase_or_treatment_output",
            statement=(
                "This module emits no kinase state, generic all-omics fusion, "
                "treatment recommendation, or protein subtype estimate."
            ),
        ),
        Limitation(
            code="provisional_abi_pending_owner_confirmation",
            statement=(
                "The M08-06 ABI, calibration policy, and M08-05 handoff remain provisional "
                "pending owner confirmation."
            ),
        ),
    )


class M0806UncertaintyDecompositionEngine:
    """Bind M08-05 evidence and abstain until coverage is review-locked."""

    __slots__ = ("_kernel",)

    def __init__(self, kernel: M0806UncertaintyKernel | None = None) -> None:
        self._kernel = kernel or M0806UncertaintyKernel()

    def decompose(
        self,
        request: object,
    ) -> TranscriptProteinUncertaintyDecompositionResult:
        preflight_m0806_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        return self._result(validated)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> TranscriptProteinUncertaintyDecompositionResult:
        """Validate digest closure and optionally replay the exact immutable request."""

        if isinstance(result, BaseModel) and not verify_result_digest(result):
            raise M0806ReplayVerificationError("result digest does not match canonical payload")
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M0806ReplayVerificationError("result is not a strict result envelope") from error
        if not verify_result_digest(validated):
            raise M0806ReplayVerificationError("result digest does not match canonical payload")
        if replay:
            expected = self.decompose(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M0806ReplayVerificationError("replayed request produced a different result")
        return validated

    def _result(
        self,
        request: DecomposeTranscriptProteinUncertaintyRequest,
    ) -> TranscriptProteinUncertaintyDecompositionResult:
        request_hash = canonical_request_digest(request)
        policy_hash = sha256_digest(request.policy)
        finding = UncertaintyFinding(
            finding_id=f"finding.{request_hash.removeprefix('sha256:')}",
            code=UncertaintyFindingCode.CALIBRATION_NOT_LOCKED,
            message=(
                "Owner-confirmed calibration and synthetic, internal, and external "
                "coverage evidence are not locked."
            ),
            evidence=_evidence(request),
        )
        sensitivity: SensitivityEnvelope = self._kernel.sensitivity_envelope(request.policy)
        payload: dict[str, object] = {
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M0806_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": UncertaintyDecompositionStatus.ABSTAINED,
            "decomposition": None,
            "sensitivity_envelope": sensitivity,
            "findings": (finding,),
            "abstention_reason": finding.message,
            "parent_target": M0806_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="m0806_uncertainty_review_required",
                rationale=(
                    "Coverage, calibration, and transport evidence require owner review "
                    "before any decomposition is released."
                ),
            ),
            "uncertainty": expected_uncertainty(),
            "provenance": expected_provenance(request, request_hash, policy_hash),
            "evidence": _evidence(request),
            "limitations": _limitations(),
            "human_review_required": True,
        }
        constructed = TranscriptProteinUncertaintyDecompositionResult.model_construct(
            **payload,  # type: ignore[arg-type]
        )
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)


def decompose_transcript_protein_uncertainty(
    request: object,
) -> TranscriptProteinUncertaintyDecompositionResult:
    """Public provisional M08-06 operation."""

    return M0806UncertaintyDecompositionEngine().decompose(request)


__all__ = [
    "M0806AuthorizationError",
    "M0806ReplayVerificationError",
    "M0806UncertaintyDecompositionEngine",
    "decompose_transcript_protein_uncertainty",
    "preflight_m0806_authorization",
]
