"""Opaque parse-once plugin boundary for M20-08."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m20_08 import (
    MonitorProteinSubtypeTranslationHealthRequest,
    ProteinSubtypeTranslationHealthResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes

from .service import M2008Service

_REQUEST_ADAPTER: Final = TypeAdapter(MonitorProteinSubtypeTranslationHealthRequest)
_TOKENS: WeakKeyDictionary[ValidatedM2008Request, object] = WeakKeyDictionary()


class ValidatedM2008Request:
    """Opaque token coupling one validated request to this plugin instance."""

    __slots__ = ("__weakref__", "_request_bytes", "_request_identity", "_seal", "request")

    def __init__(
        self,
        request: MonitorProteinSubtypeTranslationHealthRequest,
        seal: object,
        request_bytes: bytes = b"",
    ) -> None:
        self.request = request
        self._request_identity = id(request)
        self._request_bytes = request_bytes
        self._seal = seal


class M2008TokenError(TypeError):
    """A plugin token was forged, mutated, or issued by another plugin."""

    def __init__(self) -> None:
        super().__init__("M20-08 requires a validated request token")


@dataclass(frozen=True, slots=True)
class M2008PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M20-08"
    operation: str = "monitor_protein_subtype_translation_health"
    output_media_type: str = "application/vnd.glio-proteogen.m20-08+json"
    upstream_media_type: str = "application/vnd.glio-proteogen.m20-07+json"
    parent_target: str = "protein subtype"
    owner: str = "Bioinformatics"
    safety_class: str = "S2"
    evidence_gate: str = "G5"
    provisional_abi: bool = True
    external_content_traversal: bool = False
    all_omics_fusion: bool = False
    kinase_activity: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    consent_inference: bool = False
    unsupported_to_negative: bool = False
    explicit_abstention: bool = True


class M2008Plugin:
    """Strict plugin with non-forgeable validation token."""

    __slots__ = ("_seal", "_service")
    descriptor: Final = M2008PluginDescriptor()

    def __init__(self, service: M2008Service | None = None) -> None:
        self._service = service or M2008Service()
        self._seal = object()

    def validate(self, request: object) -> ValidatedM2008Request:
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        token = ValidatedM2008Request(
            validated,
            self._seal,
            canonical_json_bytes(validated.model_dump(mode="json")),
        )
        _TOKENS[token] = self._seal
        return token

    def validate_request(self, request: object) -> MonitorProteinSubtypeTranslationHealthRequest:
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def run(self, token: ValidatedM2008Request) -> ProteinSubtypeTranslationHealthResult:
        if not isinstance(token, ValidatedM2008Request) or _TOKENS.get(token) is not self._seal:
            raise M2008TokenError
        if (
            token._seal is not self._seal
            or type(token.request) is not MonitorProteinSubtypeTranslationHealthRequest
            or id(token.request) != token._request_identity
        ):
            raise M2008TokenError
        if canonical_json_bytes(token.request.model_dump(mode="json")) != token._request_bytes:
            raise M2008TokenError
        return self._service._engine.infer(token.request)

    def verify(self, result: object) -> ProteinSubtypeTranslationHealthResult:
        return self._service.verify(result)

    def replay(self, result: object) -> ProteinSubtypeTranslationHealthResult:
        return self.verify(result)


__all__ = [
    "M2008Plugin",
    "M2008PluginDescriptor",
    "M2008TokenError",
    "ValidatedM2008Request",
]
