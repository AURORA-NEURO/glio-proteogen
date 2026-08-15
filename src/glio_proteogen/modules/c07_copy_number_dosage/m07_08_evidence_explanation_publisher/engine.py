"""Deterministic, replay-verifiable M07-08 evidence publisher engine.

The dossier gives this module a behavioral brief, not a frozen ABI.  The
engine therefore implements the safety-critical behavior (opaque attribution,
control preflight, explicit abstention, and canonical replay) while keeping
all operation names and media types explicitly provisional.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import BaseModel, TypeAdapter

from glio_proteogen.contracts.m07_08 import (
    M0708_CONTRACT_VERSION,
    M0708_EVIDENCE_CLAIM,
    M0708_PARENT,
    EvidencePublicationStatus,
    ProteotypeEvidencePublicationResult,
    PublisherFindingCode,
    PublishProteotypeEvidenceRequest,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m07_08.canonical import (
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

_REQUEST_ADAPTER: Final = TypeAdapter(PublishProteotypeEvidenceRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteotypeEvidencePublicationResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class M0708EvidencePublisherAuthorizationError(PermissionError):
    """Seven caller-owned controls are not authorized for publication."""

    def __init__(self) -> None:
        super().__init__(
            "M07-08 requires accepted controls, resolved identity, and granted consent"
        )


class M0708ReplayVerificationError(ValueError):
    """A result cannot be reconstructed from its exact request envelope."""

    def __init__(self, detail: str) -> None:
        super().__init__(f"M07-08 replay verification failed: {detail}")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_evidence_publisher_authorization(candidate: object) -> None:
    """Check controls before strict validation or any opaque input traversal."""

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
        raise M0708EvidencePublisherAuthorizationError from None
    if states != expected:
        raise M0708EvidencePublisherAuthorizationError


def _prepare(candidate: object) -> object:
    preflight_evidence_publisher_authorization(candidate)
    return candidate


def _evidence(request: PublishProteotypeEvidenceRequest) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M0708_EVIDENCE_CLAIM)
        for artifact in (
            request.upstream_result,
            *(source.artifact for source in request.source_artifacts),
        )
    )


def _support() -> SupportDecision:
    return SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code="m0708_publication_review_required",
        rationale=(
            "Owner-confirmed attribution, reconstruction, and publication gates remain pending."
        ),
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="evidence_publisher_only",
            statement="Output is limited to versioned evidence and explanation metadata.",
        ),
        Limitation(
            code="no_parent_emission",
            statement=(
                "This module emits no proteotype, kinase state, generic omics fusion, "
                "or treatment recommendation."
            ),
        ),
        Limitation(
            code="opaque_external_payloads",
            statement="External evidence is referenced by digest and never traversed or relabeled.",
        ),
        Limitation(
            code="provisional_abi_pending_owner_confirmation",
            statement="M07-08 symbols, media types, and endpoint remain provisional.",
        ),
    )


class M0708EvidencePublisherEngine:
    """Authorize, abstain safely, and provide a canonical replay receipt."""

    __slots__ = ()

    def publish(self, request: object) -> ProteotypeEvidencePublicationResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
        self,
        request: PublishProteotypeEvidenceRequest,
    ) -> ProteotypeEvidencePublicationResult:
        request_hash = canonical_request_digest(request)
        evidence = _evidence(request)
        reason = (
            "Publication is abstained until M07-07 attribution, assumptions, counter-evidence, "
            "and reconstruction evidence are owner-locked."
        )
        payload: dict[str, object] = {
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M0708_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": EvidencePublicationStatus.ABSTAINED,
            "bundle": None,
            "explanation": None,
            "findings": (PublisherFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,),
            "abstention_reason": reason,
            "parent_target": M0708_PARENT,
            "support_decision": _support(),
            "uncertainty": expected_uncertainty(),
            "provenance": expected_provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _limitations(),
            "human_review_required": True,
        }
        constructed = ProteotypeEvidencePublicationResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteotypeEvidencePublicationResult:
        """Verify the receipt, embedded request digest, and optional replay."""

        if isinstance(result, BaseModel):
            if not verify_result_digest(result):
                raise M0708ReplayVerificationError(  # noqa: TRY003
                    "result digest does not match canonical payload"
                )
            embedded_request = getattr(result, "request", None)
            embedded_digest = getattr(result, "request_digest", None)
            if embedded_request is not None and embedded_digest != canonical_request_digest(
                embedded_request
            ):
                raise M0708ReplayVerificationError(  # noqa: TRY003
                    "request digest does not match embedded request"
                )
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M0708ReplayVerificationError(  # noqa: TRY003
                "result is not a strict result envelope"
            ) from error
        if not verify_result_digest(validated):
            raise M0708ReplayVerificationError(  # noqa: TRY003
                "result digest does not match canonical payload"
            )
        if validated.request_digest != canonical_request_digest(validated.request):
            raise M0708ReplayVerificationError(  # noqa: TRY003
                "request digest does not match embedded request"
            )
        if replay:
            expected = self.publish(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M0708ReplayVerificationError(  # noqa: TRY003
                    "replayed request produced a different result"
                )
        return validated


def publish_proteotype_evidence(
    request: object,
) -> ProteotypeEvidencePublicationResult:
    """Public provisional M07-08 operation."""

    return M0708EvidencePublisherEngine().publish(request)


__all__ = [
    "M0708EvidencePublisherAuthorizationError",
    "M0708EvidencePublisherEngine",
    "M0708ReplayVerificationError",
    "preflight_evidence_publisher_authorization",
    "publish_proteotype_evidence",
]
