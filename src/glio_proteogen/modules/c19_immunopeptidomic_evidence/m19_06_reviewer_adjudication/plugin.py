"""Sealed M19-06 plugin descriptor and typed entry points."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from glio_proteogen.contracts.m19_06 import (
    AdjudicateProteotypeQueueRequest,
    ProteotypeAdjudicationResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes

from .engine import M1906Engine


@dataclass(frozen=True, slots=True)
class M1906PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M19-06"
    operation: str = "adjudicate_proteotype_discrepancy_queue"
    output_media_type: str = "application/vnd.glio-proteogen.m19-06+json"
    parent_target: str = "proteotype"
    owner: str = "Platform engineering"
    safety_class: str = "S2"
    evidence_gate: str = "G4"
    provisional_abi: bool = True
    external_content_traversal: bool = False
    all_omics_fusion: bool = False
    kinase_activity: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    consent_inference: bool = False
    disagreement_erasure: bool = False
    unsupported_to_negative: bool = False
    blinded_review: bool = True
    immutable_history: bool = True
    explicit_abstention: bool = True


@dataclass(frozen=True, slots=True)
class ValidatedM1906Request:
    """Instance-bound capability for a strictly validated queue request."""

    request: AdjudicateProteotypeQueueRequest
    _seal: object
    _request_bytes: bytes
    _request_identity: int


class M1906TokenError(ValueError):
    """Raised when a forged, stale, or cross-plugin token is executed."""

    def __init__(self) -> None:
        super().__init__("M19-06 requires a token produced by this plugin")


class M1906Plugin:
    """Expose only bounded adjudication and exact replay."""

    descriptor: Final = M1906PluginDescriptor()

    def __init__(self) -> None:
        self._engine = M1906Engine()
        self._seal = object()

    def validate_request(self, candidate: object) -> AdjudicateProteotypeQueueRequest:
        return self._engine.validate_request(candidate)

    def validate(self, candidate: object) -> ValidatedM1906Request:
        request = self._engine.validate_request(candidate)
        return ValidatedM1906Request(
            request=request,
            _seal=self._seal,
            _request_bytes=canonical_json_bytes(request),
            _request_identity=id(request),
        )

    def run(self, request: object) -> ProteotypeAdjudicationResult:
        if not isinstance(request, ValidatedM1906Request) or request._seal is not self._seal:
            raise M1906TokenError
        if type(request.request) is not AdjudicateProteotypeQueueRequest:
            raise M1906TokenError
        if type(request._request_bytes) is not bytes or type(request._request_identity) is not int:
            raise M1906TokenError
        if id(request.request) != request._request_identity:
            raise M1906TokenError
        try:
            if canonical_json_bytes(request.request) != request._request_bytes:
                raise M1906TokenError
        except (TypeError, ValueError) as exc:
            raise M1906TokenError from exc
        return self._engine.adapt(request.request)

    def replay(self, result: ProteotypeAdjudicationResult) -> ProteotypeAdjudicationResult:
        return self._engine.replay(result)


__all__ = [
    "M1906Plugin",
    "M1906PluginDescriptor",
    "M1906TokenError",
    "ValidatedM1906Request",
]
