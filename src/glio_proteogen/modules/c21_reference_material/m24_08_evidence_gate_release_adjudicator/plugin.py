"""Strict parse-once plugin boundary for provisional M24-08."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m24_08 import (
    M2408_MAX_CANONICAL_REQUEST_BYTES,
    AdjudicateBiomarkerPanelEvidenceGateRequest,
    BiomarkerPanelEvidenceGateResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .service import M2408Service

_REQUEST_ADAPTER: Final = TypeAdapter(AdjudicateBiomarkerPanelEvidenceGateRequest)
_TOKENS: WeakKeyDictionary[ValidatedM2408Request, object] = WeakKeyDictionary()


@dataclass(frozen=True, slots=True)
class EvidenceGateSubmission:
    """Opaque submission wrapper for the strict request boundary."""

    request: object


class ValidatedM2408Request:
    """Opaque capability proving strict M24-08 request validation."""

    __slots__ = ("__weakref__", "_seal", "request")

    def __init__(self, request: AdjudicateBiomarkerPanelEvidenceGateRequest, seal: object) -> None:
        self.request = request
        self._seal = seal


class M2408TokenError(TypeError):
    """A plugin token was forged or issued by another plugin."""

    def __init__(self) -> None:
        super().__init__("M24-08 execution requires a validated request token")


@dataclass(frozen=True, slots=True)
class M2408PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M24-08"
    operation: str = "adjudicate_biomarker_panel_evidence_gate"
    output_media_type: str = "application/vnd.glio-proteogen.m24-08+json"
    parent_target: str = "biomarker panel"
    owner: str = "Data engineering"
    safety_class: str = "S3"
    evidence_gate: str = "G5"
    provisional_abi: bool = True
    traceability: bool = True
    risk_controls: bool = True
    claim_ceiling: bool = True
    signed_release_record: bool = True
    post_release_obligations: bool = True
    unsupported_to_negative: bool = False
    kinase_activity: bool = False
    all_omics_fusion: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    consent_inference: bool = False


class M2408Plugin:
    """Expose validate-then-run without an authority or parse bypass."""

    __slots__ = ("_seal", "_service")
    descriptor: Final = M2408PluginDescriptor()

    def __init__(self, service: M2408Service | None = None) -> None:
        self._service = service or M2408Service()
        self._seal = object()

    def validate(self, submission: EvidenceGateSubmission) -> ValidatedM2408Request:
        if not isinstance(submission, EvidenceGateSubmission):
            raise M2408TokenError
        candidate = submission.request
        if isinstance(candidate, (bytes, bytearray, str)):
            decoded = strict_json_loads(candidate, max_bytes=M2408_MAX_CANONICAL_REQUEST_BYTES)
            candidate = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        validated = self._service.validate_request(candidate)
        token = ValidatedM2408Request(validated, self._seal)
        _TOKENS[token] = self._seal
        return token

    def validate_request(self, request: object) -> AdjudicateBiomarkerPanelEvidenceGateRequest:
        return self._service.validate_request(request)

    def run(self, token: ValidatedM2408Request) -> BiomarkerPanelEvidenceGateResult:
        if not isinstance(token, ValidatedM2408Request) or _TOKENS.get(token) is not self._seal:
            raise M2408TokenError
        if token._seal is not self._seal:
            raise M2408TokenError
        return self._service.adjudicate(token.request)

    def replay(self, result: object) -> BiomarkerPanelEvidenceGateResult:
        return self._service.replay(result)


__all__ = [
    "EvidenceGateSubmission",
    "M2408Plugin",
    "M2408PluginDescriptor",
    "M2408TokenError",
    "ValidatedM2408Request",
]
