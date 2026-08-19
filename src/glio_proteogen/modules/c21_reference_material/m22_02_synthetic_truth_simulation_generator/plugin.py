"""Strict parse-once plugin boundary for provisional M22-02."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m22_02 import (
    M2202_MAX_CANONICAL_REQUEST_BYTES,
    GenerateProteinRnaDiscordanceSyntheticTruthRequest,
    ProteinRnaDiscordanceSyntheticTruthResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2202_authorization

if TYPE_CHECKING:
    from .service import M2202Service

_REQUEST_ADAPTER: Final = TypeAdapter(GenerateProteinRnaDiscordanceSyntheticTruthRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M22-02",
    title="Synthetic truth simulation generator (provisional)",
    version="0.1.0-provisional",
    owner="Data engineering",
    safety_class="S3",
    gate="G1",
    prohibited_outputs=(
        "protein-RNA discordance biological truth claim",
        "KINOPHOS kinase-state ownership",
        "generic all-omics fusion or treatment recommendation",
        "identity or consent inference",
        "unsupported-to-negative inference",
        "raw scientific-content traversal or upstream mutation",
    ),
)


@dataclass(frozen=True, slots=True)
class SyntheticTruthSubmission:
    """Opaque submission wrapper for the strict request boundary."""

    request: object


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM2202Request:
    """Opaque capability proving strict M22-02 request validation."""

    request: GenerateProteinRnaDiscordanceSyntheticTruthRequest
    _seal: object


_TOKENS: Final[
    WeakKeyDictionary[
        ValidatedM2202Request,
        tuple[object, GenerateProteinRnaDiscordanceSyntheticTruthRequest, bytes],
    ]
] = WeakKeyDictionary()


def _canonical_request_bytes(request: GenerateProteinRnaDiscordanceSyntheticTruthRequest) -> bytes:
    return canonical_json_bytes(request.model_dump(mode="json"))


def _token_is_issued(token: ValidatedM2202Request, seal: object) -> bool:
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


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M22-02 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M22-02 validation requires a synthetic-truth submission")


class M2202Plugin(
    ModulePlugin[object, ValidatedM2202Request, ProteinRnaDiscordanceSyntheticTruthResult]
):
    """Expose validate-then-generate without a parse or authority bypass."""

    __slots__ = ("_seal", "_service")

    def __init__(self, service: M2202Service) -> None:
        self._service = service
        self._seal = object()

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2202Request:
        if not isinstance(request, SyntheticTruthSubmission):
            raise _InvalidSubmissionError
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=M2202_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2202_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        validated = self._service.validate_request(candidate)
        token = ValidatedM2202Request(request=validated, _seal=self._seal)
        _TOKENS[token] = (self._seal, validated, _canonical_request_bytes(validated))
        return token

    def run(self, request: ValidatedM2202Request) -> ProteinRnaDiscordanceSyntheticTruthResult:
        if (
            type(request) is not ValidatedM2202Request
            or request._seal is not self._seal
            or not _token_is_issued(request, self._seal)
        ):
            raise _InvalidExecutionTokenError
        return self._service.generate(request.request)

    def replay(
        self,
        result: ProteinRnaDiscordanceSyntheticTruthResult,
    ) -> ProteinRnaDiscordanceSyntheticTruthResult:
        return self._service.verify_replay(result)


__all__ = ["M2202Plugin", "SyntheticTruthSubmission", "ValidatedM2202Request"]
