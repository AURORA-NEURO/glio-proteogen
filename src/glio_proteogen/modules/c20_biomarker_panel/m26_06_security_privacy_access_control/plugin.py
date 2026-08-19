"""Strict parse-once plugin boundary for M26-06 security evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m26_06 import (
    M2606_MAX_CANONICAL_REQUEST_BYTES,
    EvaluateProteomicsSecurityAccessRequest,
    ProteomicsSecurityAccessResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2606_authorization
from .service import M2606SecurityService

_REQUEST_ADAPTER: Final[TypeAdapter[EvaluateProteomicsSecurityAccessRequest]] = TypeAdapter(
    EvaluateProteomicsSecurityAccessRequest
)
_TOKENS: WeakKeyDictionary[ValidatedM2606Request, object] = WeakKeyDictionary()


@dataclass(frozen=True, slots=True)
class SecuritySubmission:
    """Opaque submission wrapper required before validation."""

    request: object


class ValidatedM2606Request:
    """Opaque capability proving strict request validation and preflight."""

    __slots__ = ("__weakref__", "_request_bytes", "_request_identity", "_seal", "request")

    def __init__(self, request: EvaluateProteomicsSecurityAccessRequest, seal: object) -> None:
        self.request = request
        self._request_identity = id(request)
        self._request_bytes = canonical_json_bytes(request.model_dump(mode="json"))
        self._seal = seal


class M2606TokenError(TypeError):
    """A security token was forged or issued by another plugin instance."""

    def __init__(self) -> None:
        super().__init__("M26-06 execution requires a validated request token")


@dataclass(frozen=True, slots=True)
class M2606PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M26-06"
    operation: str = "evaluate_proteomics_security_access"
    parent_target: str = "protein subtype"
    owner: str = "Data engineering"
    safety_class: str = "S3"
    gate: str = "G4"
    provisional_abi: bool = True
    least_privilege: bool = True
    encryption: bool = True
    secrets_management: bool = True
    isolation: bool = True
    consent_enforcement: bool = True
    de_identification: bool = True
    audit: bool = True
    threat_detection: bool = True
    unsupported_to_negative: bool = False
    identity_inference: bool = False
    consent_inference: bool = False
    treatment_recommendation: bool = False
    kinase_activity: bool = False
    all_omics_fusion: bool = False


class M2606SecurityPlugin:
    """Expose validate-then-evaluate without parser or authority bypass."""

    __slots__ = ("_seal", "_service")
    descriptor: Final = M2606PluginDescriptor()

    def __init__(self, service: M2606SecurityService | None = None) -> None:
        self._service = service or M2606SecurityService()
        self._seal = object()

    def validate(self, submission: SecuritySubmission) -> ValidatedM2606Request:
        if not isinstance(submission, SecuritySubmission):
            raise M2606TokenError
        candidate = submission.request
        if isinstance(candidate, (bytes, bytearray, str)):
            decoded = strict_json_loads(candidate, max_bytes=M2606_MAX_CANONICAL_REQUEST_BYTES)
            candidate = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
            preflight_m2606_authorization(candidate)
            validated = candidate
        else:
            validated = self._service.validate_request(candidate)
        token = ValidatedM2606Request(validated, self._seal)
        _TOKENS[token] = self._seal
        return token

    def validate_request(self, request: object) -> EvaluateProteomicsSecurityAccessRequest:
        return self._service.validate_request(request)

    def run(self, token: ValidatedM2606Request) -> ProteomicsSecurityAccessResult:
        if not isinstance(token, ValidatedM2606Request) or _TOKENS.get(token) is not self._seal:
            raise M2606TokenError
        if token._seal is not self._seal:
            raise M2606TokenError
        if type(token.request) is not EvaluateProteomicsSecurityAccessRequest:
            raise M2606TokenError
        if id(token.request) != token._request_identity:
            raise M2606TokenError
        try:
            current_bytes = canonical_json_bytes(token.request.model_dump(mode="json"))
        except Exception as error:
            raise M2606TokenError from error
        if current_bytes != token._request_bytes:
            raise M2606TokenError
        return self._service._execute_validated(token.request)

    def replay(self, result: object) -> ProteomicsSecurityAccessResult:
        return self._service.verify(result)


__all__ = [
    "M2606PluginDescriptor",
    "M2606SecurityPlugin",
    "M2606TokenError",
    "SecuritySubmission",
    "ValidatedM2606Request",
]
