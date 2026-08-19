"""Strict parse-once plugin boundary for M27-04 gateway material."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m27_04 import (
    M2704_MAX_CANONICAL_REQUEST_BYTES,
    ComplexActivityAccessSurfaceResult,
    PublishComplexActivityAccessSurfaceRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2704_authorization
from .service import M2704Service

_REQUEST_ADAPTER: Final = TypeAdapter(PublishComplexActivityAccessSurfaceRequest)
_TOKENS: WeakKeyDictionary[ValidatedM2704Request, object] = WeakKeyDictionary()


@dataclass(frozen=True, slots=True)
class GatewaySubmission:
    """Opaque gateway request wrapper."""

    request: object


class ValidatedM2704Request:
    """Opaque capability proving strict M27-04 validation."""

    __slots__ = ("__weakref__", "_request_bytes", "_request_identity", "_seal", "request")

    def __init__(self, request: PublishComplexActivityAccessSurfaceRequest, seal: object) -> None:
        self.request = request
        self._request_identity = id(request)
        self._request_bytes = canonical_json_bytes(request.model_dump(mode="json"))
        self._seal = seal


class M2704TokenError(TypeError):
    """A gateway token was forged or issued by another plugin."""

    def __init__(self) -> None:
        super().__init__("M27-04 execution requires a validated request token")


@dataclass(frozen=True, slots=True)
class M2704PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M27-04"
    operation: str = "publish_complex_activity_access_surface"
    parent_target: str = "complex activity"
    owner: str = "Clinical science"
    safety_class: str = "S3"
    gate: str = "G2"
    provisional_abi: bool = True
    typed_operations: bool = True
    authorization: bool = True
    idempotency: bool = True
    asynchronous_jobs: bool = True
    compatibility: bool = True
    signed_release_bundle_fallback: bool = True
    unsupported_to_negative: bool = False
    kinase_activity: bool = False
    all_omics_fusion: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    consent_inference: bool = False


class M2704Plugin:
    """Expose validate-then-publish without parse or authority bypass."""

    __slots__ = ("_seal", "_service")
    descriptor: Final = M2704PluginDescriptor()

    def __init__(self, service: M2704Service | None = None) -> None:
        self._service = service or M2704Service()
        self._seal = object()

    def validate(self, submission: GatewaySubmission) -> ValidatedM2704Request:
        if not isinstance(submission, GatewaySubmission):
            raise M2704TokenError
        candidate = submission.request
        if isinstance(candidate, (bytes, bytearray, str)):
            decoded = strict_json_loads(candidate, max_bytes=M2704_MAX_CANONICAL_REQUEST_BYTES)
            candidate = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
            preflight_m2704_authorization(candidate)
            validated = candidate
        else:
            validated = self._service.validate_request(candidate)
        token = ValidatedM2704Request(validated, self._seal)
        _TOKENS[token] = self._seal
        return token

    def validate_request(self, request: object) -> PublishComplexActivityAccessSurfaceRequest:
        return self._service.validate_request(request)

    def run(self, token: ValidatedM2704Request) -> ComplexActivityAccessSurfaceResult:
        if not isinstance(token, ValidatedM2704Request) or _TOKENS.get(token) is not self._seal:
            raise M2704TokenError
        if token._seal is not self._seal:
            raise M2704TokenError
        if type(token.request) is not PublishComplexActivityAccessSurfaceRequest:
            raise M2704TokenError
        if id(token.request) != token._request_identity:
            raise M2704TokenError
        try:
            current_bytes = canonical_json_bytes(token.request.model_dump(mode="json"))
        except Exception as error:
            raise M2704TokenError from error
        if current_bytes != token._request_bytes:
            raise M2704TokenError
        return self._service.publish(token.request)

    def replay(self, result: object) -> ComplexActivityAccessSurfaceResult:
        return self._service.replay(result)


__all__ = [
    "GatewaySubmission",
    "M2704Plugin",
    "M2704PluginDescriptor",
    "M2704TokenError",
    "ValidatedM2704Request",
]
