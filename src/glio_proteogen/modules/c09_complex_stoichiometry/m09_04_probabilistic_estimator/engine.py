"""Deterministic, safe-abstaining provisional M09-04 estimator."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m09_04 import (
    M0904_CONTRACT_VERSION,
    M0904_EVIDENCE_CLAIM,
    M0904_PARENT,
    EstimateComplexActivityProbabilisticRequest,
    EstimateComplexActivityProbabilisticResult,
    OptimizationDiagnostic,
    OptimizationDiagnosticStatus,
    ProbabilisticResultStatus,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m09_04.canonical import (
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

_REQUEST_ADAPTER: Final = TypeAdapter(EstimateComplexActivityProbabilisticRequest)
_RESULT_ADAPTER: Final = TypeAdapter(EstimateComplexActivityProbabilisticResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class M0904AuthorizationError(PermissionError):
    """Seven upstream controls are not authorized for this operation."""

    def __init__(self) -> None:
        super().__init__(
            "M09-04 requires accepted controls, resolved identity, and granted consent"
        )


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m0904_authorization(candidate: object) -> None:
    """Check seven controls before opening the complete M09-03 handoff."""

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
        raise M0904AuthorizationError from None
    if states != expected:
        raise M0904AuthorizationError


def _evidence(
    request: EstimateComplexActivityProbabilisticRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M0904_EVIDENCE_CLAIM)
        for artifact in request.source_artifacts
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="probabilistic_estimator_only",
            statement=("Output is limited to a typed complex-activity posterior and diagnostics."),
        ),
        Limitation(
            code="no_kinase_or_treatment_output",
            statement=(
                "This module emits no kinase state, treatment recommendation, "
                "or parent complex activity."
            ),
        ),
        Limitation(
            code="provisional_abi_pending_owner_confirmation",
            statement=(
                "The M09-04 ABI and posterior calibration are provisional "
                "pending owner confirmation."
            ),
        ),
    )


class M0904ProbabilisticEstimator:
    """Bind M09-03 and abstain until training, calibration, and diagnostics lock."""

    __slots__ = ()

    def estimate(
        self,
        request: object,
    ) -> EstimateComplexActivityProbabilisticResult:
        preflight_m0904_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        request_hash = canonical_request_digest(validated)
        configuration_hash = sha256_digest(validated.configuration)
        diagnostic = OptimizationDiagnostic(
            diagnostic_id=f"diagnostic.{request_hash.removeprefix('sha256:')}",
            status=OptimizationDiagnosticStatus.NOT_EVALUABLE,
            objective=validated.configuration.objective,
            iteration_count=0,
            message="Owner-confirmed probabilistic training and calibration are not locked.",
        )
        payload: dict[str, object] = {
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M0904_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": validated,
            "status": ProbabilisticResultStatus.ABSTAINED,
            "estimates": (),
            "diagnostics": (diagnostic,),
            "abstention_reason": diagnostic.message,
            "parent_target": M0904_PARENT,
            "support_decision": SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="m0904_probabilistic_review_required",
                rationale="Training, calibration, and optimization evidence require owner review.",
            ),
            "uncertainty": expected_uncertainty(),
            "provenance": expected_provenance(validated, request_hash, configuration_hash),
            "evidence": _evidence(validated),
            "limitations": _limitations(),
        }
        constructed = EstimateComplexActivityProbabilisticResult.model_construct(
            **payload,  # type: ignore[arg-type]
        )
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)


def estimate_complex_activity_probabilistic(
    request: object,
) -> EstimateComplexActivityProbabilisticResult:
    """Public provisional M09-04 operation."""

    return M0904ProbabilisticEstimator().estimate(request)


__all__ = [
    "M0904AuthorizationError",
    "M0904ProbabilisticEstimator",
    "estimate_complex_activity_probabilistic",
    "preflight_m0904_authorization",
]
