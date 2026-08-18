"""Deterministic, safe-abstaining provisional M06-08 publisher engine."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import BaseModel, TypeAdapter

from glio_proteogen.contracts.m06_08 import (
    M0608_CONTRACT_VERSION,
    M0608_EVIDENCE_CLAIM,
    M0608_PARENT,
    EvidencePublicationStatus,
    ProteinAbundanceEvidencePublicationResult,
    PublisherFindingCode,
    PublishProteinAbundanceEvidenceRequest,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m06_08.canonical import (
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

_REQUEST_ADAPTER: Final = TypeAdapter(PublishProteinAbundanceEvidenceRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinAbundanceEvidencePublicationResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class M0608EvidencePublisherAuthorizationError(PermissionError):
    """Seven upstream controls are not authorized for this operation."""

    def __init__(self) -> None:
        super().__init__(
            "M06-08 requires accepted controls, resolved identity, and granted consent"
        )


class M0608ReplayVerificationError(ValueError):
    """A result cannot be reconstructed from its exact request envelope."""

    def __init__(self, detail: str) -> None:
        super().__init__(f"M06-08 replay verification failed: {detail}")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_evidence_publisher_authorization(candidate: object) -> None:
    """Check controls before strict validation or upstream traversal."""

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
        raise M0608EvidencePublisherAuthorizationError from None
    if states != expected:
        raise M0608EvidencePublisherAuthorizationError


def _prepare(candidate: object) -> object:
    preflight_evidence_publisher_authorization(candidate)
    return candidate


def _evidence(request: PublishProteinAbundanceEvidenceRequest) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M0608_EVIDENCE_CLAIM)
        for artifact in (request.upstream_result, *request.source_artifacts)
    )


def _support() -> SupportDecision:
    return SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code="m0608_publication_review_required",
        rationale=(
            "Owner-confirmed publication, attribution, and reconstruction gates are pending review."
        ),
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="evidence_publisher_only",
            statement="Output is limited to evidence and explanation publication metadata.",
        ),
        Limitation(
            code="no_parent_panel_emission",
            statement=(
                "This module emits no biomarker panel, proteotype, kinase state, "
                "or treatment advice."
            ),
        ),
        Limitation(
            code="provisional_abi_pending_owner_confirmation",
            statement=(
                "The M06-08 ABI and reconstruction policy are provisional pending "
                "owner confirmation."
            ),
        ),
    )


class M0608EvidencePublisherEngine:
    """Bind an upstream reference and abstain until publisher gates are locked."""

    __slots__ = ()

    def publish(self, request: object) -> ProteinAbundanceEvidencePublicationResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
        self,
        request: PublishProteinAbundanceEvidenceRequest,
    ) -> ProteinAbundanceEvidencePublicationResult:
        request_hash = canonical_request_digest(request)
        evidence = _evidence(request)
        finding = PublisherFindingCode.PROVISIONAL_ABI_PENDING_REVIEW
        reason = (
            "Publication is abstained until M06-07 attribution, assumptions, counter-evidence, "
            "and reconstruction evidence are owner-locked."
        )
        provenance = expected_provenance(request, request_hash)
        payload: dict[str, object] = {
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M0608_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": EvidencePublicationStatus.ABSTAINED,
            "bundle": None,
            "explanation": None,
            "findings": (finding,),
            "abstention_reason": reason,
            "parent_target": M0608_PARENT,
            "support_decision": _support(),
            "uncertainty": expected_uncertainty(),
            "provenance": provenance,
            "evidence": evidence,
            "limitations": _limitations(),
            "human_review_required": True,
        }
        constructed = ProteinAbundanceEvidencePublicationResult.model_construct(
            **payload,  # type: ignore[arg-type]
        )
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinAbundanceEvidencePublicationResult:
        """Strictly verify the envelope and replay its request.

        ``replay`` remains accepted for source compatibility with provisional
        callers, but cannot disable semantic reconstruction. A digest-only
        receipt check would accept a forged nested payload after an attacker
        recomputed ``result_digest``.
        """

        del replay

        if isinstance(result, BaseModel):
            if not verify_result_digest(result):
                raise M0608ReplayVerificationError(  # noqa: TRY003
                    "result digest does not match canonical payload"
                )
            embedded_request = getattr(result, "request", None)
            embedded_digest = getattr(result, "request_digest", None)
            if embedded_request is not None and embedded_digest != canonical_request_digest(
                embedded_request
            ):
                raise M0608ReplayVerificationError(  # noqa: TRY003
                    "request digest does not match embedded request"
                )
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M0608ReplayVerificationError("result is not a strict result envelope") from error  # noqa: TRY003
        if not verify_result_digest(validated):
            raise M0608ReplayVerificationError("result digest does not match canonical payload")  # noqa: TRY003
        if validated.request_digest != canonical_request_digest(validated.request):
            raise M0608ReplayVerificationError("request digest does not match embedded request")  # noqa: TRY003
        expected = self.publish(validated.request)
        if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
            raise M0608ReplayVerificationError("replayed request produced a different result")  # noqa: TRY003
        return validated


def publish_protein_abundance_evidence(
    request: object,
) -> ProteinAbundanceEvidencePublicationResult:
    """Public provisional M06-08 operation."""

    return M0608EvidencePublisherEngine().publish(request)


__all__ = [
    "M0608EvidencePublisherAuthorizationError",
    "M0608EvidencePublisherEngine",
    "M0608ReplayVerificationError",
    "preflight_evidence_publisher_authorization",
    "publish_protein_abundance_evidence",
]
