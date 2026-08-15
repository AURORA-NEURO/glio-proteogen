"""Deterministic, safe-abstaining provisional M06-06 engine."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m06_06 import (
    M0606_CONTRACT_VERSION,
    M0606_EVIDENCE_CLAIM,
    M0606_PARENT,
    DecomposeProteinAbundanceUncertaintyRequest,
    ProteinAbundanceUncertaintyDecompositionResult,
    UncertaintyDecompositionStatus,
    UncertaintyFinding,
    UncertaintyFindingCode,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m06_06.canonical import (
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
from glio_proteogen.modules.c06_protein_abundance.m06_06_uncertainty_decomposition.kernel import (
    M0606UncertaintyDecompositionKernel,
)

_REQUEST_ADAPTER: Final = TypeAdapter(DecomposeProteinAbundanceUncertaintyRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinAbundanceUncertaintyDecompositionResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class M0606UncertaintyDecompositionAuthorizationError(PermissionError):
    """Seven upstream controls are not authorized for this operation."""

    def __init__(self) -> None:
        super().__init__(
            "M06-06 requires accepted controls, resolved identity, and granted consent"
        )


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_uncertainty_decomposition_authorization(candidate: object) -> None:
    """Check controls before opening the complete upstream M06-05 result."""

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
        raise M0606UncertaintyDecompositionAuthorizationError from None
    if states != expected:
        raise M0606UncertaintyDecompositionAuthorizationError


def _prepare(candidate: object) -> object:
    preflight_uncertainty_decomposition_authorization(candidate)
    return candidate


def _evidence(
    request: DecomposeProteinAbundanceUncertaintyRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M0606_EVIDENCE_CLAIM)
        for artifact in request.source_artifacts
    )


def _support(status: SupportStatus) -> SupportDecision:
    if status is SupportStatus.UNSUPPORTED:
        return SupportDecision(
            status=status,
            reason_code="m0606_uncertainty_abstained",
            rationale="The uncertainty estimator cannot safely emit unsupported components.",
        )
    return SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code="m0606_uncertainty_review_required",
        rationale="Owner-confirmed calibration and benchmark evidence are pending review.",
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
                "This module emits no kinase state, treatment recommendation, or parent panel."
            ),
        ),
        Limitation(
            code="provisional_abi_pending_owner_confirmation",
            statement=(
                "The M06-06 ABI and calibration policy are provisional pending owner confirmation."
            ),
        ),
    )


class M0606UncertaintyDecompositionEngine:
    """Bind M06-05 and abstain until calibration and sensitivity are review-locked."""

    __slots__ = ("_kernel",)

    def __init__(self, kernel: M0606UncertaintyDecompositionKernel | None = None) -> None:
        self._kernel = kernel or M0606UncertaintyDecompositionKernel()

    def decompose(
        self,
        request: object,
    ) -> ProteinAbundanceUncertaintyDecompositionResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
        self,
        request: DecomposeProteinAbundanceUncertaintyRequest,
    ) -> ProteinAbundanceUncertaintyDecompositionResult:
        request_hash = canonical_request_digest(request)
        policy_hash = sha256_digest(request.policy)
        upstream_status = request.constraint_result.support_decision.status
        support_status = (
            SupportStatus.UNSUPPORTED
            if upstream_status in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
            and request.constraint_result.status.value == "abstained"
            else SupportStatus.REVIEW_REQUIRED
        )
        code = (
            UncertaintyFindingCode.UPSTREAM_ABSTAINED
            if request.constraint_result.status.value == "abstained"
            else UncertaintyFindingCode.CALIBRATION_NOT_LOCKED
        )
        finding = UncertaintyFinding(
            finding_id=f"finding.{request_hash.removeprefix('sha256:')}",
            code=code,
            message=(
                "The bound upstream result is abstained."
                if code is UncertaintyFindingCode.UPSTREAM_ABSTAINED
                else "Owner-confirmed calibration and benchmark coverage are not locked."
            ),
            evidence=_evidence(request),
        )
        sensitivity = self._kernel.sensitivity_envelope(request.policy)
        provenance = expected_provenance(request, request_hash, policy_hash)
        payload: dict[str, object] = {
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M0606_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": UncertaintyDecompositionStatus.ABSTAINED,
            "decomposition": None,
            "sensitivity_envelope": sensitivity,
            "findings": (finding,),
            "abstention_reason": finding.message,
            "parent_target": M0606_PARENT,
            "support_decision": _support(support_status),
            "uncertainty": expected_uncertainty(),
            "provenance": provenance,
            "evidence": _evidence(request),
            "limitations": _limitations(),
            "human_review_required": True,
        }
        constructed = ProteinAbundanceUncertaintyDecompositionResult.model_construct(
            **payload,  # type: ignore[arg-type]
        )
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)


def decompose_protein_abundance_uncertainty(
    request: object,
) -> ProteinAbundanceUncertaintyDecompositionResult:
    """Public provisional M06-06 operation."""

    return M0606UncertaintyDecompositionEngine().decompose(request)


__all__ = [
    "M0606UncertaintyDecompositionAuthorizationError",
    "M0606UncertaintyDecompositionEngine",
    "decompose_protein_abundance_uncertainty",
    "preflight_uncertainty_decomposition_authorization",
]
