"""Opaque parse-once plugin boundary for provisional M21-04."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final
from weakref import WeakKeyDictionary

from .service import M2104Service

if TYPE_CHECKING:
    from glio_proteogen.contracts.m21_04 import (
        ComplexActivityExternalTransportResult,
        EvaluateComplexActivityExternalTransportRequest,
    )

_TOKENS: WeakKeyDictionary[ValidatedM2104Request, object] = WeakKeyDictionary()


class ValidatedM2104Request:
    """Opaque token coupling one validated request to one plugin instance."""

    __slots__ = ("__weakref__", "_seal", "request")

    def __init__(
        self, request: EvaluateComplexActivityExternalTransportRequest, seal: object
    ) -> None:
        self.request = request
        self._seal = seal


class M2104TokenError(TypeError):
    """A plugin token was forged or issued by another plugin."""

    def __init__(self) -> None:
        super().__init__("M21-04 requires a validated request token")


@dataclass(frozen=True, slots=True)
class M2104PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M21-04"
    operation: str = "evaluate_complex_activity_external_transport"
    output_media_type: str = "application/vnd.glio-proteogen.m21-04+json"
    upstream_media_type: str = "application/vnd.glio-proteogen.m21-03+json"
    parent_target: str = "complex activity"
    owner: str = "Platform engineering"
    safety_class: str = "S3"
    evidence_gate: str = "G3"
    provisional_abi: bool = True
    external_transport: bool = True
    unsupported_to_negative: bool = False
    kinase_activity: bool = False
    all_omics_fusion: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    consent_inference: bool = False


class M2104Plugin:
    """Strict plugin with non-forgeable validation token."""

    __slots__ = ("_seal", "_service")
    descriptor: Final = M2104PluginDescriptor()

    def __init__(self, service: M2104Service | None = None) -> None:
        self._service = service or M2104Service()
        self._seal = object()

    def validate(self, request: object) -> ValidatedM2104Request:
        validated = self._service.validate_request(request)
        token = ValidatedM2104Request(validated, self._seal)
        _TOKENS[token] = self._seal
        return token

    def validate_request(self, request: object) -> EvaluateComplexActivityExternalTransportRequest:
        return self._service.validate_request(request)

    def run(self, token: ValidatedM2104Request) -> ComplexActivityExternalTransportResult:
        if not isinstance(token, ValidatedM2104Request) or _TOKENS.get(token) is not self._seal:
            raise M2104TokenError
        if token._seal is not self._seal:
            raise M2104TokenError
        return self._service._engine.evaluate(token.request)

    def replay(self, result: object) -> ComplexActivityExternalTransportResult:
        return self._service.replay(result)


__all__ = [
    "M2104Plugin",
    "M2104PluginDescriptor",
    "M2104TokenError",
    "ValidatedM2104Request",
]
