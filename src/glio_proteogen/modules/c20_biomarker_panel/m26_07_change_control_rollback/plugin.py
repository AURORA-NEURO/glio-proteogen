"""Strict parse-once M26-07 plugin boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m26_07 import (
    M2607_MAX_CANONICAL_REQUEST_BYTES,
    ControlProteinSubtypeChangeRequest,
    ProteinSubtypeChangeControlResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .service import M2607ChangeControlService

_REQUEST_ADAPTER: Final[TypeAdapter[ControlProteinSubtypeChangeRequest]] = TypeAdapter(
    ControlProteinSubtypeChangeRequest
)
_TOKENS: WeakKeyDictionary[ValidatedM2607Request, object] = WeakKeyDictionary()


@dataclass(frozen=True, slots=True)
class RollbackSubmission:
    request: object


class ValidatedM2607Request:
    __slots__ = ("__weakref__", "_seal", "request")

    def __init__(self, request: ControlProteinSubtypeChangeRequest, seal: object) -> None:
        self.request = request
        self._seal = seal


class M2607TokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M26-07 execution requires a validated request token")


@dataclass(frozen=True, slots=True)
class M2607PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M26-07"
    operation: str = "control_protein_subtype_change_and_rollback"
    parent_target: str = "protein subtype"
    owner: str = "Platform engineering"
    safety_class: str = "S3"
    gate: str = "G5"
    provisional_abi: bool = True
    change_classification: bool = True
    revalidation: bool = True
    champion_challenger: bool = True
    staged_rollout: bool = True
    tested_rollback: bool = True
    unsupported_to_negative: bool = False
    kinase_activity: bool = False
    all_omics_fusion: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    consent_inference: bool = False


class M2607Plugin:
    __slots__ = ("_seal", "_service")
    descriptor: Final[M2607PluginDescriptor] = M2607PluginDescriptor()

    def __init__(self, service: M2607ChangeControlService | None = None) -> None:
        self._service = service or M2607ChangeControlService()
        self._seal = object()

    def validate(self, submission: RollbackSubmission) -> ValidatedM2607Request:
        if not isinstance(submission, RollbackSubmission):
            raise M2607TokenError
        candidate = submission.request
        if isinstance(candidate, (bytes, bytearray, str)):
            decoded = strict_json_loads(candidate, max_bytes=M2607_MAX_CANONICAL_REQUEST_BYTES)
            candidate = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        validated = self._service.validate_request(candidate)
        token = ValidatedM2607Request(validated, self._seal)
        _TOKENS[token] = self._seal
        return token

    def run(self, token: ValidatedM2607Request) -> ProteinSubtypeChangeControlResult:
        if not isinstance(token, ValidatedM2607Request) or _TOKENS.get(token) is not self._seal:
            raise M2607TokenError
        if token._seal is not self._seal:
            raise M2607TokenError
        return self._service.control(token.request)

    def replay(self, result: object) -> ProteinSubtypeChangeControlResult:
        return self._service.verify(result)


__all__ = [
    "M2607Plugin",
    "M2607PluginDescriptor",
    "M2607TokenError",
    "RollbackSubmission",
    "ValidatedM2607Request",
]
