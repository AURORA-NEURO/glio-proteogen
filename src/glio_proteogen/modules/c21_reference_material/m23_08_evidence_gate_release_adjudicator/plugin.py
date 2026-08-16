"""Strict parse-once plugin boundary for provisional M23-08."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m23_08 import (
    M2308_MAX_CANONICAL_REQUEST_BYTES,
    AdjudicateVariantPeptideEvidenceGateRequest,
    VariantPeptideEvidenceGateResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .service import M2308Service

_REQUEST_ADAPTER: Final = TypeAdapter(AdjudicateVariantPeptideEvidenceGateRequest)
_TOKENS: WeakKeyDictionary[ValidatedM2308Request, object] = WeakKeyDictionary()


@dataclass(frozen=True, slots=True)
class EvidenceGateSubmission:
    """Opaque submission wrapper for the strict request boundary."""

    request: object


class ValidatedM2308Request:
    """Opaque capability proving strict M23-08 request validation."""

    __slots__ = ("__weakref__", "_seal", "request")

    def __init__(
        self, request: AdjudicateVariantPeptideEvidenceGateRequest, seal: object
    ) -> None:
        self.request = request
        self._seal = seal


class M2308TokenError(TypeError):
    """A plugin token was forged or issued by another plugin."""

    def __init__(self) -> None:
        super().__init__("M23-08 execution requires a validated request token")


@dataclass(frozen=True, slots=True)
class M2308PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M23-08"
    operation: str = "adjudicate_variant_peptide_evidence_gate"
    output_media_type: str = "application/vnd.glio-proteogen.m23-08+json"
    parent_target: str = "variant peptide"
    owner: str = "Clinical science"
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


class M2308Plugin:
    """Expose validate-then-run without an authority or parse bypass."""

    __slots__ = ("_seal", "_service")
    descriptor: Final = M2308PluginDescriptor()

    def __init__(self, service: M2308Service | None = None) -> None:
        self._service = service or M2308Service()
        self._seal = object()

    def validate(self, submission: EvidenceGateSubmission) -> ValidatedM2308Request:
        if not isinstance(submission, EvidenceGateSubmission):
            raise M2308TokenError
        candidate = submission.request
        if isinstance(candidate, (bytes, bytearray, str)):
            decoded = strict_json_loads(candidate, max_bytes=M2308_MAX_CANONICAL_REQUEST_BYTES)
            candidate = _REQUEST_ADAPTER.validate_json(
                canonical_json_bytes(decoded), strict=True
            )
        validated = self._service.validate_request(candidate)
        token = ValidatedM2308Request(validated, self._seal)
        _TOKENS[token] = self._seal
        return token

    def validate_request(
        self, request: object
    ) -> AdjudicateVariantPeptideEvidenceGateRequest:
        return self._service.validate_request(request)

    def run(self, token: ValidatedM2308Request) -> VariantPeptideEvidenceGateResult:
        if not isinstance(token, ValidatedM2308Request) or _TOKENS.get(token) is not self._seal:
            raise M2308TokenError
        if token._seal is not self._seal:
            raise M2308TokenError
        return self._service.adjudicate(token.request)

    def replay(self, result: object) -> VariantPeptideEvidenceGateResult:
        return self._service.replay(result)


__all__ = [
    "EvidenceGateSubmission",
    "M2308Plugin",
    "M2308PluginDescriptor",
    "M2308TokenError",
    "ValidatedM2308Request",
]
