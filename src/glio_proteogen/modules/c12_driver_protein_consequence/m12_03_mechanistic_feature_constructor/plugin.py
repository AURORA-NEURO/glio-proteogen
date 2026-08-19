"""Strict validate-once plugin boundary for M12-03."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from glio_proteogen.contracts.m12_03 import (
    M1203_CONTRACT_VERSION,
    M1203_MAX_CANONICAL_REQUEST_BYTES,
    BiomarkerPanelMechanisticFeatureResult,
    ConstructBiomarkerPanelMechanisticFeaturesRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import request_digest_for, validate_json_request

if TYPE_CHECKING:
    from .service import M1203Service

_TOKEN_SEAL: Final = object()
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M12-03",
    title="Mechanistic feature constructor",
    version=M1203_CONTRACT_VERSION,
    owner="Clinical science",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "KINOPHOS kinase-state ownership",
        "generic all-omics fusion",
        "direct treatment recommendation",
        "identity or consent inference",
        "external artifact traversal or caller evidence authentication",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM1203Request:
    """Opaque capability proving strict request acceptance."""

    request: ConstructBiomarkerPanelMechanisticFeaturesRequest
    request_digest: str
    _seal: object
    _request_bytes: bytes
    _request_identity: int


class InvalidM1203ExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M12-03 execution requires a validated request token")


class M1203Plugin(
    ModulePlugin[object, ValidatedM1203Request, BiomarkerPanelMechanisticFeatureResult]
):
    """Grant one exact execution capability after strict replay validation."""

    __slots__ = ("_seal", "_service")

    def __init__(self, service: M1203Service) -> None:
        self._service = service
        self._seal = object()

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM1203Request:
        if type(request) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", request)
            decoded = strict_json_loads(
                serialized,
                max_bytes=M1203_MAX_CANONICAL_REQUEST_BYTES,
            )
            typed = validate_json_request(decoded, serialized)
        elif isinstance(request, ConstructBiomarkerPanelMechanisticFeaturesRequest):
            typed = request
        else:
            typed = self._service.validate_request(request)

        return ValidatedM1203Request(
            request=typed,
            request_digest=request_digest_for(typed),
            _seal=self._seal,
            _request_bytes=canonical_json_bytes(typed),
            _request_identity=id(typed),
        )

    def run(self, request: ValidatedM1203Request) -> BiomarkerPanelMechanisticFeatureResult:
        if type(request) is not ValidatedM1203Request or request._seal is not self._seal:
            raise InvalidM1203ExecutionTokenError
        if type(request.request) is not ConstructBiomarkerPanelMechanisticFeaturesRequest:
            raise InvalidM1203ExecutionTokenError
        if type(request.request_digest) is not str or type(request._request_bytes) is not bytes:
            raise InvalidM1203ExecutionTokenError
        if (
            type(request._request_identity) is not int
            or id(request.request) != request._request_identity
        ):
            raise InvalidM1203ExecutionTokenError
        try:
            if (
                canonical_json_bytes(request.request) != request._request_bytes
                or request_digest_for(request.request) != request.request_digest
            ):
                raise InvalidM1203ExecutionTokenError
        except (TypeError, ValueError) as exc:
            raise InvalidM1203ExecutionTokenError from exc
        if request._seal is not self._seal:
            raise InvalidM1203ExecutionTokenError
        return self._service.execute(request.request)


InvalidM1203ExecutionToken = InvalidM1203ExecutionTokenError

__all__ = [
    "InvalidM1203ExecutionToken",
    "InvalidM1203ExecutionTokenError",
    "M1203Plugin",
    "ValidatedM1203Request",
]
