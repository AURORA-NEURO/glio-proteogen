"""Deterministic, fail-closed provisional M10-04 estimator runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import BaseModel, TypeAdapter

from glio_proteogen.contracts.m10_04 import (
    M1004_CONTRACT_VERSION,
    M1004_EVIDENCE_CLAIM,
    M1004_PARENT,
    EstimateProteinRnaDiscordanceProbabilisticRequest,
    OptimizationDiagnostic,
    OptimizationDiagnosticStatus,
    ProbabilisticResultStatus,
    ProteinRnaDiscordanceProbabilisticResult,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m10_04.canonical import (
    canonical_request_digest,
    result_payload_digest,
    verify_result_digest,
)
from glio_proteogen.kernel.models import (
    EvidenceReference,
    Limitation,
    SupportDecision,
    SupportStatus,
)

_REQUEST_ADAPTER: Final = TypeAdapter(EstimateProteinRnaDiscordanceProbabilisticRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinRnaDiscordanceProbabilisticResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class M1004ProbabilisticEstimatorAuthorizationError(PermissionError):
    """Caller-owned controls are not authorized for estimation."""

    def __init__(self) -> None:
        super().__init__(
            "M10-04 requires accepted controls, resolved identity, and granted consent"
        )


class M1004ReplayVerificationError(ValueError):
    """A result cannot be reconstructed from its exact request envelope."""

    def __init__(self, detail: str) -> None:
        super().__init__(f"M10-04 replay verification failed: {detail}")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_probabilistic_estimator_authorization(candidate: object) -> None:
    """Check seven control decisions before strict model validation."""

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
        raise M1004ProbabilisticEstimatorAuthorizationError from None
    if states != expected:
        raise M1004ProbabilisticEstimatorAuthorizationError


def _prepare(candidate: object) -> object:
    preflight_probabilistic_estimator_authorization(candidate)
    return candidate


def _evidence(
    request: EstimateProteinRnaDiscordanceProbabilisticRequest,
) -> tuple[EvidenceReference, ...]:
    artifacts = (
        request.baseline_result,
        request.configuration.reference,
        *request.source_artifacts,
    )
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M1004_EVIDENCE_CLAIM)
        for artifact in artifacts
    )


def _diagnostic() -> OptimizationDiagnostic:
    return OptimizationDiagnostic(
        diagnostic_id="diagnostic.m1004.not-evaluable",
        status=OptimizationDiagnosticStatus.NOT_EVALUABLE,
        objective="owner-locked probabilistic objective pending",
        iteration_count=0,
        message=(
            "The provisional lane cannot claim optimization convergence until training, "
            "baseline comparison, and calibration artifacts are owner-locked."
        ),
    )


def _support() -> SupportDecision:
    return SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code="m1004_estimation_review_required",
        rationale=(
            "Posterior estimation is abstained pending owner-locked objective, training, "
            "baseline comparison, and uncertainty calibration evidence."
        ),
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="posterior_not_published",
            statement="No posterior estimate is published until optimization gates are locked.",
        ),
        Limitation(
            code="no_parent_emission",
            statement=(
                "This module emits no parent protein-RNA discordance claim, kinase state, "
                "generic all-omics fusion, or treatment advice."
            ),
        ),
        Limitation(
            code="opaque_inputs",
            statement="Inputs remain immutable artifact references and are not traversed.",
        ),
        Limitation(
            code="provisional_abi_pending_owner_confirmation",
            statement=(
                "Estimator ABI, posterior representation, and baseline handoff are provisional."
            ),
        ),
    )


class M1004ProbabilisticEstimatorEngine:
    """Bind deterministic configuration and abstain until estimator gates are locked."""

    __slots__ = ()

    def estimate(self, request: object) -> ProteinRnaDiscordanceProbabilisticResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
        self,
        request: EstimateProteinRnaDiscordanceProbabilisticRequest,
    ) -> ProteinRnaDiscordanceProbabilisticResult:
        request_hash = canonical_request_digest(request)
        payload: dict[str, object] = {
            "output_type": "protein_rna_discordance_posterior",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1004_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": ProbabilisticResultStatus.ABSTAINED,
            "estimates": (),
            "diagnostics": (_diagnostic(),),
            "abstention_reason": (
                "Estimation is abstained until M10-03 baseline comparison, optimization, "
                "calibration, and transport gates are owner-locked."
            ),
            "parent_target": M1004_PARENT,
            "support_decision": _support(),
            "uncertainty": expected_uncertainty(),
            "provenance": expected_provenance(request, request_hash),
            "evidence": _evidence(request),
            "limitations": _limitations(),
            "human_review_required": True,
        }
        constructed = ProteinRnaDiscordanceProbabilisticResult.model_construct(
            **payload,  # type: ignore[arg-type]
        )
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinRnaDiscordanceProbabilisticResult:
        """Verify receipt digests and optionally replay the exact request."""

        if isinstance(result, BaseModel):
            if not verify_result_digest(result):
                raise M1004ReplayVerificationError(  # noqa: TRY003
                    "result digest does not match canonical payload"
                )
            embedded_request = getattr(result, "request", None)
            embedded_digest = getattr(result, "request_digest", None)
            if embedded_request is not None and embedded_digest != canonical_request_digest(
                embedded_request
            ):
                raise M1004ReplayVerificationError(  # noqa: TRY003
                    "request digest does not match embedded request"
                )
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1004ReplayVerificationError(  # noqa: TRY003
                "result is not a strict result envelope"
            ) from error
        if not verify_result_digest(validated):
            raise M1004ReplayVerificationError(  # noqa: TRY003
                "result digest does not match canonical payload"
            )
        if validated.request_digest != canonical_request_digest(validated.request):
            raise M1004ReplayVerificationError(  # noqa: TRY003
                "request digest does not match embedded request"
            )
        if replay:
            expected = self.estimate(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1004ReplayVerificationError(  # noqa: TRY003
                    "replayed request produced a different result"
                )
        return validated


def estimate_protein_rna_discordance_probabilistic(
    request: object,
) -> ProteinRnaDiscordanceProbabilisticResult:
    """Public provisional M10-04 operation."""

    return M1004ProbabilisticEstimatorEngine().estimate(request)


__all__ = [
    "M1004ProbabilisticEstimatorAuthorizationError",
    "M1004ProbabilisticEstimatorEngine",
    "M1004ReplayVerificationError",
    "estimate_protein_rna_discordance_probabilistic",
    "preflight_probabilistic_estimator_authorization",
]
