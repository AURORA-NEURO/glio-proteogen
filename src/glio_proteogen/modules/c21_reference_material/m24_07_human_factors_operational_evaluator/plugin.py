"""Strict parse-once plugin boundary for provisional M24-07."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m24_07 import (
    M2407_MAX_CANONICAL_REQUEST_BYTES,
    BiomarkerPanelHumanFactorsResult,
    EvaluateBiomarkerPanelHumanFactorsRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2407_authorization

if TYPE_CHECKING:
    from .service import M2407Service

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateBiomarkerPanelHumanFactorsRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M24-07",
    title="Human-factors and operational evaluator (provisional)",
    version="0.1.0-provisional",
    owner="Clinical science",
    safety_class="S3",
    gate="G4",
    prohibited_outputs=(
        "biomarker panel or biological truth claim",
        "KINOPHOS kinase-state ownership",
        "generic all-omics fusion or treatment recommendation",
        "identity or consent inference",
        "unsupported-to-negative inference",
        "raw scientific-content traversal or upstream mutation",
    ),
)


@dataclass(frozen=True, slots=True)
class HumanFactorsSubmission:
    """Opaque submission wrapper for the strict request boundary."""

    request: object


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM2407Request:
    """Opaque capability proving strict M24-07 request validation."""

    request: EvaluateBiomarkerPanelHumanFactorsRequest
    _seal: object


_TOKENS: Final[
    WeakKeyDictionary[
        ValidatedM2407Request,
        tuple[object, EvaluateBiomarkerPanelHumanFactorsRequest, bytes],
    ]
] = WeakKeyDictionary()


def _canonical_request_bytes(request: EvaluateBiomarkerPanelHumanFactorsRequest) -> bytes:
    return canonical_json_bytes(request.model_dump(mode="json"))


def _token_is_issued(token: ValidatedM2407Request, seal: object) -> bool:
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
        super().__init__("M24-07 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M24-07 validation requires a human-factors submission")


class M2407Plugin(ModulePlugin[object, ValidatedM2407Request, BiomarkerPanelHumanFactorsResult]):
    """Expose validate-then-evaluate without a parse or authority bypass."""

    __slots__ = ("_seal", "_service")

    def __init__(self, service: M2407Service) -> None:
        self._service = service
        self._seal = object()

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2407Request:
        if not isinstance(request, HumanFactorsSubmission):
            raise _InvalidSubmissionError
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=M2407_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2407_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        validated = self._service.validate_request(candidate)
        token = ValidatedM2407Request(request=validated, _seal=self._seal)
        _TOKENS[token] = (self._seal, validated, _canonical_request_bytes(validated))
        return token

    def run(self, request: ValidatedM2407Request) -> BiomarkerPanelHumanFactorsResult:
        if (
            type(request) is not ValidatedM2407Request
            or request._seal is not self._seal
            or not _token_is_issued(request, self._seal)
        ):
            raise _InvalidExecutionTokenError
        return self._service.evaluate(request.request)

    def replay(
        self,
        result: BiomarkerPanelHumanFactorsResult,
    ) -> BiomarkerPanelHumanFactorsResult:
        return self._service.verify_replay(result)


__all__ = ["HumanFactorsSubmission", "M2407Plugin", "ValidatedM2407Request"]
