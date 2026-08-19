"""Strict parse-once plugin boundary for M26-05 telemetry emission."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m26_05 import (
    M2605_MAX_CANONICAL_REQUEST_BYTES,
    EmitProteomicsTelemetryRequest,
    ProteomicsTelemetryResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .service import M2605ObservabilityService

_REQUEST_ADAPTER: Final[TypeAdapter[EmitProteomicsTelemetryRequest]] = TypeAdapter(
    EmitProteomicsTelemetryRequest
)
_TOKENS: WeakKeyDictionary[ValidatedM2605Request, object] = WeakKeyDictionary()


@dataclass(frozen=True, slots=True)
class TelemetrySubmission:
    """Opaque input wrapper used to make the plugin boundary explicit."""

    request: object


class ValidatedM2605Request:
    """Opaque capability proving strict M26-05 validation and authorization."""

    __slots__ = ("__weakref__", "_request_bytes", "_request_identity", "_seal", "request")

    def __init__(
        self, request: EmitProteomicsTelemetryRequest, seal: object, request_bytes: bytes
    ) -> None:
        self.request = request
        self._request_identity = id(request)
        self._request_bytes = request_bytes
        self._seal = seal


class M2605TokenError(TypeError):
    """A telemetry token was forged or issued by another plugin."""

    def __init__(self) -> None:
        super().__init__("M26-05 execution requires a validated request token")


@dataclass(frozen=True, slots=True)
class M2605PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M26-05"
    operation: str = "emit_proteomics_observability_telemetry"
    parent_target: str = "protein subtype"
    owner: str = "Clinical science"
    safety_class: str = "S3"
    gate: str = "G4"
    provisional_abi: bool = True
    typed_operations: bool = True
    authorization: bool = True
    idempotency: bool = True
    replay_verification: bool = True
    reviewer_actions: bool = True
    unsupported_to_negative: bool = False
    kinase_activity: bool = False
    all_omics_fusion: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    consent_inference: bool = False


class M2605Plugin:
    """Expose validate-then-emit without a parse or authority bypass."""

    __slots__ = ("_seal", "_service")
    descriptor: Final[M2605PluginDescriptor] = M2605PluginDescriptor()

    def __init__(self, service: M2605ObservabilityService | None = None) -> None:
        self._service = service or M2605ObservabilityService()
        self._seal = object()

    def validate(self, submission: TelemetrySubmission) -> ValidatedM2605Request:
        if not isinstance(submission, TelemetrySubmission):
            raise M2605TokenError
        candidate = submission.request
        if isinstance(candidate, (bytes, bytearray, str)):
            decoded = strict_json_loads(candidate, max_bytes=M2605_MAX_CANONICAL_REQUEST_BYTES)
            candidate = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        validated = self._service.validate_request(candidate)
        if type(validated) is not EmitProteomicsTelemetryRequest:
            raise M2605TokenError
        request_bytes = canonical_json_bytes(validated.model_dump(mode="json"))
        token = ValidatedM2605Request(validated, self._seal, request_bytes)
        _TOKENS[token] = self._seal
        return token

    def validate_request(self, request: object) -> EmitProteomicsTelemetryRequest:
        """Validate an already-decoded request for service integrations."""

        return self._service.validate_request(request)

    def run(self, token: ValidatedM2605Request) -> ProteomicsTelemetryResult:
        if not isinstance(token, ValidatedM2605Request) or _TOKENS.get(token) is not self._seal:
            raise M2605TokenError
        if (
            token._seal is not self._seal
            or type(token.request) is not EmitProteomicsTelemetryRequest
            or id(token.request) != token._request_identity
        ):
            raise M2605TokenError
        try:
            current_bytes = canonical_json_bytes(token.request.model_dump(mode="json"))
        except Exception as error:
            raise M2605TokenError from error
        if current_bytes != token._request_bytes:
            raise M2605TokenError
        return self._service.execute(token.request)

    def replay(self, result: object) -> ProteomicsTelemetryResult:
        """Verify a result's canonical request/result closure."""

        return self._service.verify(result)


__all__ = [
    "M2605Plugin",
    "M2605PluginDescriptor",
    "M2605TokenError",
    "TelemetrySubmission",
    "ValidatedM2605Request",
]
