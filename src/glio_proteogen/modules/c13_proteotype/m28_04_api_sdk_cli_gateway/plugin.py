"""Strict parse-once plugin boundary for M28-04 gateway material."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m28_04 import (
    M2804_MAX_CANONICAL_REQUEST_BYTES,
    ProteinRnaDiscordanceAccessSurfaceResult,
    PublishProteinRnaDiscordanceAccessSurfaceRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .service import M2804Service

_REQUEST_ADAPTER: Final = TypeAdapter(PublishProteinRnaDiscordanceAccessSurfaceRequest)
_TOKENS: WeakKeyDictionary[ValidatedM2804Request, object] = WeakKeyDictionary()


@dataclass(frozen=True, slots=True)
class GatewaySubmission:
    """Opaque gateway request wrapper."""

    request: object


class ValidatedM2804Request:
    """Opaque capability proving strict M28-04 validation."""

    __slots__ = ("__weakref__", "_seal", "request")

    def __init__(
        self, request: PublishProteinRnaDiscordanceAccessSurfaceRequest, seal: object
    ) -> None:
        self.request = request
        self._seal = seal


class M2804TokenError(TypeError):
    """A gateway token was forged or issued by another plugin."""

    def __init__(self) -> None:
        super().__init__("M28-04 execution requires a validated request token")


@dataclass(frozen=True, slots=True)
class M2804PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M28-04"
    operation: str = "publish_protein_rna_discordance_access_surface"
    parent_target: str = "protein-RNA discordance"
    owner: str = "Data engineering"
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


class M2804Plugin:
    """Expose validate-then-publish without parse or authority bypass."""

    __slots__ = ("_seal", "_service")
    descriptor: Final = M2804PluginDescriptor()

    def __init__(self, service: M2804Service | None = None) -> None:
        self._service = service or M2804Service()
        self._seal = object()

    def validate(self, submission: GatewaySubmission) -> ValidatedM2804Request:
        if not isinstance(submission, GatewaySubmission):
            raise M2804TokenError
        candidate = submission.request
        if isinstance(candidate, (bytes, bytearray, str)):
            decoded = strict_json_loads(candidate, max_bytes=M2804_MAX_CANONICAL_REQUEST_BYTES)
            candidate = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        validated = self._service.validate_request(candidate)
        token = ValidatedM2804Request(validated, self._seal)
        _TOKENS[token] = self._seal
        return token

    def validate_request(self, request: object) -> PublishProteinRnaDiscordanceAccessSurfaceRequest:
        return self._service.validate_request(request)

    def run(self, token: ValidatedM2804Request) -> ProteinRnaDiscordanceAccessSurfaceResult:
        if not isinstance(token, ValidatedM2804Request) or _TOKENS.get(token) is not self._seal:
            raise M2804TokenError
        if token._seal is not self._seal:
            raise M2804TokenError
        return self._service.publish(token.request)

    def replay(self, result: object) -> ProteinRnaDiscordanceAccessSurfaceResult:
        return self._service.replay(result)


__all__ = [
    "GatewaySubmission",
    "M2804Plugin",
    "M2804PluginDescriptor",
    "M2804TokenError",
    "ValidatedM2804Request",
]
