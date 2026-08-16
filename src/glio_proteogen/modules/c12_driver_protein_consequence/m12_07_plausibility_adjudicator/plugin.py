"""Strict parse-once plugin boundary for M12-07."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m12_07 import (
    M1207_MAX_CANONICAL_REQUEST_BYTES,
    AdjudicateBiomarkerPanelPlausibilityRequest,
    BiomarkerPanelPlausibilityAdjudicationResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import (
    preflight_m1207_authorization,
)

if TYPE_CHECKING:
    from .service import (
        M1207Service,
    )

_REQUEST_ADAPTER: Final = TypeAdapter(AdjudicateBiomarkerPanelPlausibilityRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M12-07",
    title="Plausibility and negative-control adjudicator",
    version="0.1.0-provisional",
    owner="Computational biology",
    safety_class="S2",
    gate="G3",
    prohibited_outputs=(
        "kinase activity or kinase-state ownership",
        "generic all-omics fusion or direct treatment recommendation",
        "identity or consent inference",
        "unsupported-to-negative conversion or disagreement erasure",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM1207Request:
    """Capability token issued by exactly one plugin instance."""

    request: AdjudicateBiomarkerPanelPlausibilityRequest
    issuer: object


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M12-07 execution requires a validated request token")


class M1207Plugin(
    ModulePlugin[object, ValidatedM1207Request, BiomarkerPanelPlausibilityAdjudicationResult]
):
    """Parse strict JSON once, then execute only an issuer-bound token."""

    __slots__ = ("_service",)

    def __init__(self, service: M1207Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM1207Request:
        candidate = request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(
                candidate,
                max_bytes=M1207_MAX_CANONICAL_REQUEST_BYTES,
            )
            preflight_m1207_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(
                canonical_json_bytes(decoded),
                strict=True,
            )
        validated = self._service.validate_request(candidate)
        return ValidatedM1207Request(request=validated, issuer=self)

    def run(
        self,
        request: ValidatedM1207Request,
    ) -> BiomarkerPanelPlausibilityAdjudicationResult:
        if not isinstance(request, ValidatedM1207Request) or request.issuer is not self:
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M1207Plugin", "ValidatedM1207Request"]
