"""Strict parse-once plugin boundary for M26-04 gateway material."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m26_04 import (
    M2604_MAX_CANONICAL_REQUEST_BYTES,
    ProteinSubtypeAccessSurfaceResult,
    PublishProteinSubtypeAccessSurfaceRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2604_authorization
from .service import M2604Service

_REQUEST_ADAPTER: Final = TypeAdapter(PublishProteinSubtypeAccessSurfaceRequest)
_TOKENS: WeakKeyDictionary[
    ValidatedM2604Request,
    tuple[object, PublishProteinSubtypeAccessSurfaceRequest, bytes],
] = WeakKeyDictionary()


@dataclass(frozen=True, slots=True)
class GatewaySubmission:
    """Opaque gateway request wrapper."""

    request: object


class ValidatedM2604Request:
    """Opaque capability proving strict M26-04 validation."""

    __slots__ = ("__weakref__", "_request_bytes", "_request_identity", "_seal", "request")

    def __init__(self, request: PublishProteinSubtypeAccessSurfaceRequest, seal: object) -> None:
        self.request = request
        self._request_identity = id(request)
        self._request_bytes = canonical_json_bytes(request.model_dump(mode="json"))
        self._seal = seal


def _canonical_request_bytes(request: PublishProteinSubtypeAccessSurfaceRequest) -> bytes:
    return canonical_json_bytes(request.model_dump(mode="json"))


def _token_is_issued(token: ValidatedM2604Request, seal: object) -> bool:
    try:
        snapshot = _TOKENS.get(token)
        current = _canonical_request_bytes(token.request)
    except (TypeError, ValueError):
        return False
    return (
        snapshot is not None
        and snapshot[0] is seal
        and snapshot[1] is token.request
        and snapshot[2] == current
    )


class M2604TokenError(TypeError):
    """A gateway token was forged or issued by another plugin."""

    def __init__(self) -> None:
        super().__init__("M26-04 execution requires a validated request token")


@dataclass(frozen=True, slots=True)
class M2604PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M26-04"
    operation: str = "publish_protein_subtype_access_surface"
    parent_target: str = "protein subtype"
    owner: str = "Quality engineering"
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


class M2604Plugin:
    """Expose validate-then-publish without parse or authority bypass."""

    __slots__ = ("_seal", "_service")
    descriptor: Final = M2604PluginDescriptor()

    def __init__(self, service: M2604Service | None = None) -> None:
        self._service = service or M2604Service()
        self._seal = object()

    def validate(self, submission: GatewaySubmission) -> ValidatedM2604Request:
        if not isinstance(submission, GatewaySubmission):
            raise M2604TokenError
        candidate = submission.request
        if isinstance(candidate, (bytes, bytearray, str)):
            decoded = strict_json_loads(candidate, max_bytes=M2604_MAX_CANONICAL_REQUEST_BYTES)
            candidate = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
            preflight_m2604_authorization(candidate)
            validated = candidate
        else:
            validated = self._service.validate_request(candidate)
        token = ValidatedM2604Request(validated, self._seal)
        _TOKENS[token] = (self._seal, validated, _canonical_request_bytes(validated))
        return token

    def validate_request(self, request: object) -> PublishProteinSubtypeAccessSurfaceRequest:
        return self._service.validate_request(request)

    def run(self, token: ValidatedM2604Request) -> ProteinSubtypeAccessSurfaceResult:
        if (
            not isinstance(token, ValidatedM2604Request)
            or token._seal is not self._seal
            or not _token_is_issued(token, self._seal)
        ):
            raise M2604TokenError
        if type(token.request) is not PublishProteinSubtypeAccessSurfaceRequest:
            raise M2604TokenError
        if id(token.request) != token._request_identity:
            raise M2604TokenError
        try:
            current_bytes = canonical_json_bytes(token.request.model_dump(mode="json"))
        except Exception as error:
            raise M2604TokenError from error
        if current_bytes != token._request_bytes:
            raise M2604TokenError
        return self._service._publish_validated(token.request)

    def replay(self, result: object) -> ProteinSubtypeAccessSurfaceResult:
        return self._service.replay(result)


__all__ = [
    "GatewaySubmission",
    "M2604Plugin",
    "M2604PluginDescriptor",
    "M2604TokenError",
    "ValidatedM2604Request",
]
