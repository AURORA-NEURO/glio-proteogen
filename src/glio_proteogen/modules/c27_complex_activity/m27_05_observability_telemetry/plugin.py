"""Strict parse-once M27-05 plugin boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m27_05 import (
    M2705_MAX_CANONICAL_REQUEST_BYTES,
    EmitProteomicsTelemetryRequest,
    ProteomicsTelemetryResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .service import M2705Service

_REQUEST_ADAPTER: Final = TypeAdapter(EmitProteomicsTelemetryRequest)
_TOKENS: WeakKeyDictionary[ValidatedM2705Request, object] = WeakKeyDictionary()


@dataclass(frozen=True, slots=True)
class TelemetrySubmission:
    """Opaque external M27-05 request wrapper."""

    request: object


class ValidatedM2705Request:
    """Opaque capability proving strict M27-05 request validation."""

    __slots__ = ("__weakref__", "_seal", "request")

    def __init__(self, request: EmitProteomicsTelemetryRequest, seal: object) -> None:
        self.request = request
        self._seal = seal


class M2705TokenError(TypeError):
    """A telemetry token was forged or issued by another plugin."""

    def __init__(self) -> None:
        super().__init__("M27-05 execution requires a validated request token")


@dataclass(frozen=True, slots=True)
class M2705PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M27-05"
    operation: str = "emit_search_quant_observability_telemetry"
    parent_target: str = "complex activity"
    owner: str = "Data engineering"
    safety_class: str = "S3"
    gate: str = "G4"
    provisional_abi: bool = True
    telemetry_retention: bool = True
    dashboards: bool = True
    alert_states: bool = True
    unsupported_to_negative: bool = False
    biological_claims: bool = False


class M2705Plugin:
    """Expose validate-then-emit without authority or parse bypass."""

    __slots__ = ("_seal", "_service")
    descriptor: Final = M2705PluginDescriptor()

    def __init__(self, service: M2705Service | None = None) -> None:
        self._service = service or M2705Service()
        self._seal = object()

    def validate(self, submission: TelemetrySubmission) -> ValidatedM2705Request:
        if not isinstance(submission, TelemetrySubmission):
            raise M2705TokenError
        candidate = submission.request
        if isinstance(candidate, (bytes, bytearray, str)):
            decoded = strict_json_loads(candidate, max_bytes=M2705_MAX_CANONICAL_REQUEST_BYTES)
            candidate = _REQUEST_ADAPTER.validate_json(
                canonical_json_bytes(decoded), strict=True
            )
        validated = self._service.validate_request(candidate)
        token = ValidatedM2705Request(validated, self._seal)
        _TOKENS[token] = self._seal
        return token

    def run(self, token: ValidatedM2705Request) -> ProteomicsTelemetryResult:
        if not isinstance(token, ValidatedM2705Request) or _TOKENS.get(token) is not self._seal:
            raise M2705TokenError
        if token._seal is not self._seal:
            raise M2705TokenError
        return self._service.emit(token.request)

    def replay(self, result: object) -> ProteomicsTelemetryResult:
        return self._service.replay(result)


__all__ = [
    "M2705Plugin",
    "M2705PluginDescriptor",
    "M2705TokenError",
    "TelemetrySubmission",
    "ValidatedM2705Request",
]
