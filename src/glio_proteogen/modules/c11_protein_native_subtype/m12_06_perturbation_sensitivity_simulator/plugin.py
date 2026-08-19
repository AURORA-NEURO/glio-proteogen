"""Strict validate-once plugin for M12-06."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m12_06 import (
    BiomarkerPanelPerturbationSensitivityResult,
    SimulateBiomarkerPanelPerturbationRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import MAX_JSON_BYTES, strict_json_loads
from glio_proteogen.modules.c11_protein_native_subtype.m12_06_perturbation_sensitivity_simulator.engine import (  # noqa: E501
    preflight_m1206_authorization,
)

if TYPE_CHECKING:
    from glio_proteogen.modules.c11_protein_native_subtype.m12_06_perturbation_sensitivity_simulator.service import (  # noqa: E501
        M1206Service,
    )

_REQUEST_ADAPTER: Final = TypeAdapter(SimulateBiomarkerPanelPerturbationRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M12-06",
    title="Perturbation and sensitivity simulator",
    version="0.1.0-provisional",
    owner="Scientific engineering",
    safety_class="S2",
    gate="G2",
    prohibited_outputs=(
        "kinase activity or KINOPHOS-owned state",
        "generic all-omics fusion",
        "direct treatment recommendation",
        "upstream evidence mutation or disagreement erasure",
        "identity or consent inference",
        "unsupported perturbation represented as a negative finding",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM1206Request:
    """Opaque capability proving strict validation and control preflight."""

    request: SimulateBiomarkerPanelPerturbationRequest
    _seal: object
    _request_bytes: bytes
    _request_identity: int


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M12-06 execution requires a validated request token")


class M1206Plugin(
    ModulePlugin[object, ValidatedM1206Request, BiomarkerPanelPerturbationSensitivityResult]
):
    """Expose M12-06 through the common plugin boundary."""

    __slots__ = ("_seal", "_service")

    def __init__(self, service: M1206Service) -> None:
        self._service = service
        self._seal = object()

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM1206Request:
        candidate = request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=MAX_JSON_BYTES)
            preflight_m1206_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        validated = self._service.validate_request(candidate)
        return ValidatedM1206Request(
            request=validated,
            _seal=self._seal,
            _request_bytes=canonical_json_bytes(validated),
            _request_identity=id(validated),
        )

    def run(self, request: ValidatedM1206Request) -> BiomarkerPanelPerturbationSensitivityResult:
        if not isinstance(request, ValidatedM1206Request):
            raise _InvalidExecutionTokenError
        if request._seal is not self._seal:
            raise _InvalidExecutionTokenError
        if type(request.request) is not SimulateBiomarkerPanelPerturbationRequest:
            raise _InvalidExecutionTokenError
        if type(request._request_bytes) is not bytes or type(request._request_identity) is not int:
            raise _InvalidExecutionTokenError
        if id(request.request) != request._request_identity:
            raise _InvalidExecutionTokenError
        try:
            if canonical_json_bytes(request.request) != request._request_bytes:
                raise _InvalidExecutionTokenError
        except (TypeError, ValueError) as exc:
            raise _InvalidExecutionTokenError from exc
        return self._service.execute(request.request)


__all__ = ["M1206Plugin", "ValidatedM1206Request"]
