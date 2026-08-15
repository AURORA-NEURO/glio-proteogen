"""Deterministic, safe-abstaining provisional M07-06 engine."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m07_06 import (
    M0706_CONTRACT_VERSION,
    M0706_EVIDENCE_CLAIM,
    M0706_PARENT,
    CopyNumberDosageUncertaintyDecompositionResult,
    DecomposeCopyNumberDosageUncertaintyRequest,
    UncertaintyDecompositionStatus,
    UncertaintyFinding,
    UncertaintyFindingCode,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m07_06.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    EvidenceReference,
    Limitation,
    SupportDecision,
    SupportStatus,
)
from glio_proteogen.modules.c07_copy_number_dosage.m07_06_uncertainty_decomposition.kernel import (
    M0706UncertaintyDecompositionKernel,
)

_REQUEST_ADAPTER: Final = TypeAdapter(DecomposeCopyNumberDosageUncertaintyRequest)
_RESULT_ADAPTER: Final = TypeAdapter(CopyNumberDosageUncertaintyDecompositionResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class M0706AuthorizationError(PermissionError):
    """Seven upstream controls are not authorized for this operation."""

    def __init__(self) -> None:
        super().__init__(
            "M07-06 requires accepted controls, resolved identity, and granted consent"
        )


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m0706_authorization(candidate: object) -> None:
    """Check controls before opening the complete M07-05 result reference."""

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
        raise M0706AuthorizationError from None
    if states != expected:
        raise M0706AuthorizationError


def _evidence(
    request: DecomposeCopyNumberDosageUncertaintyRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M0706_EVIDENCE_CLAIM)
        for artifact in request.source_artifacts
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="uncertainty_decomposition_only",
            statement="Output is limited to typed uncertainty and sensitivity metadata.",
        ),
        Limitation(
            code="no_kinase_or_treatment_output",
            statement=(
                "This module emits no kinase state, treatment recommendation, or parent proteotype."
            ),
        ),
        Limitation(
            code="provisional_abi_pending_owner_confirmation",
            statement=(
                "The M07-06 ABI and calibration policy are provisional pending owner confirmation."
            ),
        ),
    )


class M0706UncertaintyDecompositionEngine:
    """Bind M07-05 and abstain until calibration and sensitivity are review-locked."""

    __slots__ = ("_kernel",)

    def __init__(self, kernel: M0706UncertaintyDecompositionKernel | None = None) -> None:
        self._kernel = kernel or M0706UncertaintyDecompositionKernel()

    def decompose(
        self,
        request: object,
    ) -> CopyNumberDosageUncertaintyDecompositionResult:
        preflight_m0706_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        return self._result(validated)

    def _result(
        self,
        request: DecomposeCopyNumberDosageUncertaintyRequest,
    ) -> CopyNumberDosageUncertaintyDecompositionResult:
        request_hash = canonical_request_digest(request)
        policy_hash = sha256_digest(request.policy)
        finding = UncertaintyFinding(
            finding_id=f"finding.{request_hash.removeprefix('sha256:')}",
            code=UncertaintyFindingCode.CALIBRATION_NOT_LOCKED,
            message="Owner-confirmed calibration and benchmark coverage are not locked.",
            evidence=_evidence(request),
        )
        sensitivity = self._kernel.sensitivity_envelope(request.policy)
        payload: dict[str, object] = {
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M0706_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": UncertaintyDecompositionStatus.ABSTAINED,
            "decomposition": None,
            "sensitivity_envelope": sensitivity,
            "findings": (finding,),
            "abstention_reason": finding.message,
            "parent_target": M0706_PARENT,
            "support_decision": SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="m0706_uncertainty_review_required",
                rationale="Owner-confirmed calibration and benchmark evidence are pending review.",
            ),
            "uncertainty": expected_uncertainty(),
            "provenance": expected_provenance(request, request_hash, policy_hash),
            "evidence": _evidence(request),
            "limitations": _limitations(),
            "human_review_required": True,
        }
        constructed = CopyNumberDosageUncertaintyDecompositionResult.model_construct(
            **payload,  # type: ignore[arg-type]
        )
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)


def decompose_copy_number_dosage_uncertainty(
    request: object,
) -> CopyNumberDosageUncertaintyDecompositionResult:
    """Public provisional M07-06 operation."""

    return M0706UncertaintyDecompositionEngine().decompose(request)


__all__ = [
    "M0706AuthorizationError",
    "M0706UncertaintyDecompositionEngine",
    "decompose_copy_number_dosage_uncertainty",
    "preflight_m0706_authorization",
]
