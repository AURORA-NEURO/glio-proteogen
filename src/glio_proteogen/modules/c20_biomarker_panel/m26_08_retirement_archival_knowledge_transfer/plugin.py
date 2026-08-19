"""Strict parse-once M26-08 plugin boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m26_08 import (
    M2608_MAX_CANONICAL_REQUEST_BYTES,
    ProteinSubtypeRetirementResult,
    RetireProteinSubtypeServiceRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .service import M2608RetirementService

_REQUEST_ADAPTER: Final[TypeAdapter[RetireProteinSubtypeServiceRequest]] = TypeAdapter(
    RetireProteinSubtypeServiceRequest
)
_TOKENS: WeakKeyDictionary[ValidatedM2608Request, object] = WeakKeyDictionary()


@dataclass(frozen=True, slots=True)
class RetirementSubmission:
    request: object


class ValidatedM2608Request:
    __slots__ = ("__weakref__", "_request_bytes", "_request_identity", "_seal", "request")

    def __init__(
        self, request: RetireProteinSubtypeServiceRequest, seal: object, request_bytes: bytes
    ) -> None:
        self.request = request
        self._request_identity = id(request)
        self._request_bytes = request_bytes
        self._seal = seal


class M2608TokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M26-08 execution requires a validated request token")


@dataclass(frozen=True, slots=True)
class M2608PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M26-08"
    operation: str = "retire_protein_subtype_service"
    parent_target: str = "protein subtype"
    owner: str = "Scientific engineering"
    safety_class: str = "S3"
    gate: str = "G5"
    provisional_abi: bool = True
    retirement_criteria: bool = True
    dependency_migration: bool = True
    evidence_preservation: bool = True
    communication_acknowledgement: bool = True
    long_term_archive: bool = True
    signed_release_bundle_fallback: bool = True
    unsupported_to_negative: bool = False
    kinase_activity: bool = False
    all_omics_fusion: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    consent_inference: bool = False


class M2608Plugin:
    __slots__ = ("_seal", "_service")
    descriptor: Final[M2608PluginDescriptor] = M2608PluginDescriptor()

    def __init__(self, service: M2608RetirementService | None = None) -> None:
        self._service = service or M2608RetirementService()
        self._seal = object()

    def validate(self, submission: RetirementSubmission) -> ValidatedM2608Request:
        if not isinstance(submission, RetirementSubmission):
            raise M2608TokenError
        candidate = submission.request
        if isinstance(candidate, (bytes, bytearray, str)):
            decoded = strict_json_loads(candidate, max_bytes=M2608_MAX_CANONICAL_REQUEST_BYTES)
            candidate = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        validated = self._service.validate_request(candidate)
        if type(validated) is not RetireProteinSubtypeServiceRequest:
            raise M2608TokenError
        request_bytes = canonical_json_bytes(validated.model_dump(mode="json"))
        token = ValidatedM2608Request(validated, self._seal, request_bytes)
        _TOKENS[token] = self._seal
        return token

    def run(self, token: ValidatedM2608Request) -> ProteinSubtypeRetirementResult:
        if not isinstance(token, ValidatedM2608Request) or _TOKENS.get(token) is not self._seal:
            raise M2608TokenError
        if (
            token._seal is not self._seal
            or type(token.request) is not RetireProteinSubtypeServiceRequest
            or id(token.request) != token._request_identity
        ):
            raise M2608TokenError
        try:
            current_bytes = canonical_json_bytes(token.request.model_dump(mode="json"))
        except Exception as error:
            raise M2608TokenError from error
        if current_bytes != token._request_bytes:
            raise M2608TokenError
        return self._service.retire(token.request)

    def replay(self, result: object) -> ProteinSubtypeRetirementResult:
        return self._service.verify(result)


__all__ = [
    "M2608Plugin",
    "M2608PluginDescriptor",
    "M2608TokenError",
    "RetirementSubmission",
    "ValidatedM2608Request",
]
