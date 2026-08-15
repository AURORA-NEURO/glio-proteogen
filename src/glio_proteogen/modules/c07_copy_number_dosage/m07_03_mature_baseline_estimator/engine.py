"""Deterministic, safe-abstaining provisional M07-03 engine."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m07_03 import (
    M0703_CONTRACT_VERSION,
    M0703_EVIDENCE_CLAIM,
    M0703_PARENT,
    BaselineDiagnostic,
    BaselineDiagnosticStatus,
    BaselineResultStatus,
    EstimateCopyNumberDosageBaselineRequest,
    EstimateCopyNumberDosageBaselineResult,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m07_03.canonical import (
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

_REQUEST_ADAPTER: Final = TypeAdapter(EstimateCopyNumberDosageBaselineRequest)
_RESULT_ADAPTER: Final = TypeAdapter(EstimateCopyNumberDosageBaselineResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class M0703AuthorizationError(PermissionError):
    """Seven upstream controls are not authorized for this operation."""

    def __init__(self) -> None:
        super().__init__(
            "M07-03 requires accepted controls, resolved identity, and granted consent"
        )


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m0703_authorization(candidate: object) -> None:
    """Check seven controls before opening the M07-02 representation reference."""

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
        raise M0703AuthorizationError from None
    if states != expected:
        raise M0703AuthorizationError


def _evidence(request: EstimateCopyNumberDosageBaselineRequest) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M0703_EVIDENCE_CLAIM)
        for artifact in request.source_artifacts
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="copy_number_baseline_only",
            statement="Output is limited to a typed baseline estimate and diagnostics.",
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
                "The M07-03 ABI and baseline calibration are provisional "
                "pending owner confirmation."
            ),
        ),
    )


class M0703MatureBaselineEngine:
    """Bind M07-02 and abstain until baseline evidence is review-locked."""

    __slots__ = ()

    def estimate(
        self,
        request: object,
    ) -> EstimateCopyNumberDosageBaselineResult:
        preflight_m0703_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        return self._result(validated)

    def _result(
        self,
        request: EstimateCopyNumberDosageBaselineRequest,
    ) -> EstimateCopyNumberDosageBaselineResult:
        request_hash = canonical_request_digest(request)
        configuration_hash = sha256_digest(request.configuration)
        diagnostic = BaselineDiagnostic(
            diagnostic_id=f"diagnostic.{request_hash.removeprefix('sha256:')}",
            status=BaselineDiagnosticStatus.NOT_EVALUABLE,
            message="Owner-confirmed baseline implementation and calibration are not locked.",
        )
        payload: dict[str, object] = {
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M0703_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": BaselineResultStatus.ABSTAINED,
            "estimates": (),
            "diagnostics": (diagnostic,),
            "abstention_reason": diagnostic.message,
            "parent_target": M0703_PARENT,
            "support_decision": SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="m0703_baseline_review_required",
                rationale=(
                    "Baseline behavior, benchmark coverage, and calibration require owner review."
                ),
            ),
            "uncertainty": expected_uncertainty(),
            "provenance": expected_provenance(request, request_hash, configuration_hash),
            "evidence": _evidence(request),
            "limitations": _limitations(),
            "human_review_required": True,
        }
        constructed = EstimateCopyNumberDosageBaselineResult.model_construct(
            **payload,  # type: ignore[arg-type]
        )
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)


def estimate_copy_number_dosage_baseline(
    request: object,
) -> EstimateCopyNumberDosageBaselineResult:
    """Public provisional M07-03 operation."""

    return M0703MatureBaselineEngine().estimate(request)


__all__ = [
    "M0703AuthorizationError",
    "M0703MatureBaselineEngine",
    "estimate_copy_number_dosage_baseline",
    "preflight_m0703_authorization",
]
