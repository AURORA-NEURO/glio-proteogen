"""Deterministic, fail-closed provisional M10-06 runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import BaseModel, TypeAdapter

from glio_proteogen.contracts.m10_06 import (
    M1006_CONTRACT_VERSION,
    M1006_EVIDENCE_CLAIM,
    M1006_PARENT,
    DecomposeProteinRnaDiscordanceUncertaintyRequest,
    ProteinRnaDiscordanceUncertaintyDecompositionResult,
    SensitivityEnvelope,
    SensitivityEnvelopeStatus,
    UncertaintyDecompositionStatus,
    UncertaintyFinding,
    UncertaintyFindingCode,
    canonical_request_digest,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m10_06.canonical import (
    result_payload_digest,
    verify_result_digest,
)
from glio_proteogen.kernel.models import (
    EvidenceReference,
    Limitation,
    SupportDecision,
    SupportStatus,
)

_REQUEST_ADAPTER: Final = TypeAdapter(DecomposeProteinRnaDiscordanceUncertaintyRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinRnaDiscordanceUncertaintyDecompositionResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class M1006UncertaintyDecompositionAuthorizationError(PermissionError):
    """Caller-owned controls are not authorized for decomposition."""

    def __init__(self) -> None:
        super().__init__(
            "M10-06 requires accepted controls, resolved identity, and granted consent"
        )


class M1006UncertaintyDecompositionReplayError(ValueError):
    """A result cannot be reconstructed from its exact request envelope."""

    def __init__(self, detail: str) -> None:
        super().__init__(f"M10-06 replay verification failed: {detail}")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_uncertainty_decomposition_authorization(candidate: object) -> None:
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
        raise M1006UncertaintyDecompositionAuthorizationError from None
    if states != expected:
        raise M1006UncertaintyDecompositionAuthorizationError


def _prepare(candidate: object) -> object:
    preflight_uncertainty_decomposition_authorization(candidate)
    return candidate


def _evidence(
    request: DecomposeProteinRnaDiscordanceUncertaintyRequest,
) -> tuple[EvidenceReference, ...]:
    artifacts = (
        request.integrator_result,
        request.policy.calibration_reference,
        *request.source_artifacts,
    )
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M1006_EVIDENCE_CLAIM)
        for artifact in artifacts
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="decomposition_not_published",
            statement=(
                "No decomposed uncertainty components are published until calibration is locked."
            ),
        ),
        Limitation(
            code="coverage_not_evaluable",
            statement=(
                "Nominal 90 percent coverage cannot be claimed without locked benchmark evidence."
            ),
        ),
        Limitation(
            code="no_parent_emission",
            statement=(
                "This module emits no parent protein-RNA discordance claim, kinase state, "
                "generic all-omics fusion, or treatment advice."
            ),
        ),
        Limitation(
            code="provisional_abi_pending_owner_confirmation",
            statement=(
                "Uncertainty ABI, sensitivity representation, and M10-05 handoff remain "
                "provisional."
            ),
        ),
    )


def _findings(evidence: tuple[EvidenceReference, ...]) -> tuple[UncertaintyFinding, ...]:
    return tuple(
        UncertaintyFinding(
            finding_id=f"finding.m1006.{code.value}",
            code=code,
            message=message,
            evidence=evidence,
        )
        for code, message in (
            (
                UncertaintyFindingCode.CALIBRATION_NOT_LOCKED,
                "Calibration and nominal coverage evidence are not owner-locked.",
            ),
            (
                UncertaintyFindingCode.SENSITIVITY_NOT_EVALUABLE,
                "Sensitivity envelope is not evaluable before the locked benchmark lane.",
            ),
            (
                UncertaintyFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                "The uncertainty decomposition ABI awaits owner confirmation.",
            ),
        )
    )


class M1006UncertaintyDecompositionEngine:
    """Bind deterministic inputs and abstain until calibration gates are locked."""

    __slots__ = ()

    def decompose(self, request: object) -> ProteinRnaDiscordanceUncertaintyDecompositionResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
        self, request: DecomposeProteinRnaDiscordanceUncertaintyRequest
    ) -> ProteinRnaDiscordanceUncertaintyDecompositionResult:
        request_hash = canonical_request_digest(request)
        evidence = _evidence(request)
        payload: dict[str, object] = {
            "output_type": "protein_rna_discordance_uncertainty_decomposition",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1006_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": UncertaintyDecompositionStatus.ABSTAINED,
            "decomposition": None,
            "sensitivity_envelope": SensitivityEnvelope(
                status=SensitivityEnvelopeStatus.ABSTAINED,
                rationale=(
                    "Sensitivity is abstained until nominal coverage, calibration, and "
                    "transport benchmarks are owner-locked."
                ),
                evidence=evidence,
            ),
            "findings": _findings(evidence),
            "abstention_reason": (
                "Uncertainty decomposition is abstained until calibration, sensitivity, "
                "and transport gates are owner-locked."
            ),
            "parent_target": M1006_PARENT,
            "support_decision": SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="m1006_decomposition_review_required",
                rationale=(
                    "Seven uncertainty dimensions are explicit, but decomposition is not "
                    "supported before calibration and benchmark evidence are locked."
                ),
            ),
            "uncertainty": expected_uncertainty(),
            "provenance": expected_provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _limitations(),
            "human_review_required": True,
        }
        constructed = ProteinRnaDiscordanceUncertaintyDecompositionResult.model_construct(
            **payload,  # type: ignore[arg-type]
        )
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinRnaDiscordanceUncertaintyDecompositionResult:
        """Verify receipt digests and optionally replay its exact request."""

        if isinstance(result, BaseModel):
            if not verify_result_digest(result):
                raise M1006UncertaintyDecompositionReplayError(  # noqa: TRY003
                    "result digest does not match canonical payload"
                )
            embedded_request = getattr(result, "request", None)
            embedded_digest = getattr(result, "request_digest", None)
            if embedded_request is not None and embedded_digest != canonical_request_digest(
                embedded_request
            ):
                raise M1006UncertaintyDecompositionReplayError(  # noqa: TRY003
                    "request digest does not match embedded request"
                )
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1006UncertaintyDecompositionReplayError(  # noqa: TRY003
                "result is not a strict result envelope"
            ) from error
        if replay:
            expected = self.decompose(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1006UncertaintyDecompositionReplayError(  # noqa: TRY003
                    "replayed request produced a different result"
                )
        return validated


def decompose_protein_rna_discordance_uncertainty(
    request: object,
) -> ProteinRnaDiscordanceUncertaintyDecompositionResult:
    """Public provisional M10-06 operation."""

    return M1006UncertaintyDecompositionEngine().decompose(request)


__all__ = [
    "M1006UncertaintyDecompositionAuthorizationError",
    "M1006UncertaintyDecompositionEngine",
    "M1006UncertaintyDecompositionReplayError",
    "decompose_protein_rna_discordance_uncertainty",
    "preflight_uncertainty_decomposition_authorization",
]
