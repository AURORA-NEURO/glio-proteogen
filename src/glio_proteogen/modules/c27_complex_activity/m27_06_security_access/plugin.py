"""Strict parse-once M27-06 plugin boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m27_06 import (
    M2706_MAX_CANONICAL_REQUEST_BYTES,
    ComplexActivitySecurityAccessResult,
    EvaluateComplexActivitySecurityAccessRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .service import M2706Service

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateComplexActivitySecurityAccessRequest)
_TOKENS: WeakKeyDictionary[ValidatedM2706Request, object] = WeakKeyDictionary()


@dataclass(frozen=True, slots=True)
class SecuritySubmission:
    request: object


class ValidatedM2706Request:
    __slots__ = ("__weakref__", "_seal", "request")

    def __init__(self, request: EvaluateComplexActivitySecurityAccessRequest, seal: object) -> None:
        self.request = request
        self._seal = seal


class M2706TokenError(TypeError):
    """A security capability was forged or issued by another plugin."""

    def __init__(self) -> None:
        super().__init__("M27-06 execution requires a validated security request token")


@dataclass(frozen=True, slots=True)
class M2706PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M27-06"
    operation: str = "evaluate_complex_activity_security_access"
    parent_target: str = "complex activity"
    owner: str = "Platform engineering"
    safety_class: str = "S3"
    gate: str = "G4"
    provisional_abi: bool = True
    unsupported_to_negative: bool = False
    biological_claims: bool = False


class M2706Plugin:
    __slots__ = ("_seal", "_service")
    descriptor: Final = M2706PluginDescriptor()

    def __init__(self, service: M2706Service | None = None) -> None:
        self._service = service or M2706Service()
        self._seal = object()

    def validate(self, submission: SecuritySubmission) -> ValidatedM2706Request:
        if not isinstance(submission, SecuritySubmission):
            raise M2706TokenError
        candidate = submission.request
        if isinstance(candidate, (bytes, bytearray, str)):
            decoded = strict_json_loads(candidate, max_bytes=M2706_MAX_CANONICAL_REQUEST_BYTES)
            candidate = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        validated = self._service.validate_request(candidate)
        token = ValidatedM2706Request(validated, self._seal)
        _TOKENS[token] = self._seal
        return token

    def run(self, token: ValidatedM2706Request) -> ComplexActivitySecurityAccessResult:
        if not isinstance(token, ValidatedM2706Request) or _TOKENS.get(token) is not self._seal:
            raise M2706TokenError
        if token._seal is not self._seal:
            raise M2706TokenError
        return self._service.emit(token.request)

    def replay(self, result: object) -> ComplexActivitySecurityAccessResult:
        return self._service.replay(result)


__all__ = [
    "M2706Plugin",
    "M2706PluginDescriptor",
    "M2706TokenError",
    "SecuritySubmission",
    "ValidatedM2706Request",
]
