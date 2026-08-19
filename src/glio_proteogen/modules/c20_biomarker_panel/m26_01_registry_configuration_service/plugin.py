"""Strict parse-once plugin boundary for M26-01 registry material."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m26_01 import (
    M2601_MAX_CANONICAL_REQUEST_BYTES,
    ProteinSubtypeRegistryResult,
    RegisterProteinSubtypeRegistryRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .service import M2601Service

_REQUEST_ADAPTER: Final = TypeAdapter(RegisterProteinSubtypeRegistryRequest)
_TOKENS: WeakKeyDictionary[ValidatedM2601Request, object] = WeakKeyDictionary()


@dataclass(frozen=True, slots=True)
class RegistrySubmission:
    """Opaque request wrapper for the strict plugin boundary."""

    request: object


class ValidatedM2601Request:
    """Opaque capability proving strict M26-01 validation."""

    __slots__ = ("__weakref__", "_request_bytes", "_request_identity", "_seal", "request")

    def __init__(
        self, request: RegisterProteinSubtypeRegistryRequest, seal: object, request_bytes: bytes
    ) -> None:
        self.request = request
        self._request_identity = id(request)
        self._request_bytes = request_bytes
        self._seal = seal


class M2601TokenError(TypeError):
    """A plugin token was forged or issued by another plugin."""

    def __init__(self) -> None:
        super().__init__("M26-01 execution requires a validated request token")


@dataclass(frozen=True, slots=True)
class M2601PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M26-01"
    operation: str = "register_protein_subtype_registry"
    output_media_type: str = "application/vnd.glio-proteogen.m26-01+json"
    parent_target: str = "protein subtype"
    owner: str = "Computational biology"
    safety_class: str = "S3"
    gate: str = "G0"
    provisional_abi: bool = True
    immutable_history: bool = True
    active_configuration: bool = True
    unsupported_to_negative: bool = False
    kinase_activity: bool = False
    all_omics_fusion: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    consent_inference: bool = False


class M2601Plugin:
    """Expose validate-then-register without parse or authority bypass."""

    __slots__ = ("_seal", "_service")
    descriptor: Final = M2601PluginDescriptor()

    def __init__(self, service: M2601Service | None = None) -> None:
        self._service = service or M2601Service()
        self._seal = object()

    def validate(self, submission: RegistrySubmission) -> ValidatedM2601Request:
        if not isinstance(submission, RegistrySubmission):
            raise M2601TokenError
        candidate = submission.request
        if isinstance(candidate, (bytes, bytearray, str)):
            decoded = strict_json_loads(candidate, max_bytes=M2601_MAX_CANONICAL_REQUEST_BYTES)
            candidate = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        validated = self._service.validate_request(candidate)
        if type(validated) is not RegisterProteinSubtypeRegistryRequest:
            raise M2601TokenError
        request_bytes = canonical_json_bytes(validated.model_dump(mode="json"))
        token = ValidatedM2601Request(validated, self._seal, request_bytes)
        _TOKENS[token] = self._seal
        return token

    def validate_request(self, request: object) -> RegisterProteinSubtypeRegistryRequest:
        return self._service.validate_request(request)

    def run(self, token: ValidatedM2601Request) -> ProteinSubtypeRegistryResult:
        if not isinstance(token, ValidatedM2601Request) or _TOKENS.get(token) is not self._seal:
            raise M2601TokenError
        if (
            token._seal is not self._seal
            or type(token.request) is not RegisterProteinSubtypeRegistryRequest
            or id(token.request) != token._request_identity
        ):
            raise M2601TokenError
        try:
            current_bytes = canonical_json_bytes(token.request.model_dump(mode="json"))
        except Exception as error:
            raise M2601TokenError from error
        if current_bytes != token._request_bytes:
            raise M2601TokenError
        return self._service.register(token.request)

    def replay(self, result: object) -> ProteinSubtypeRegistryResult:
        return self._service.replay(result)


__all__ = [
    "M2601Plugin",
    "M2601PluginDescriptor",
    "M2601TokenError",
    "RegistrySubmission",
    "ValidatedM2601Request",
]
