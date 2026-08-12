"""Agent-friendly strict plugin boundary for M01-02."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_02.v1 import (
    IdentityLineageResolution,
    ReconcileIdentityLineageRequest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import MAX_JSON_BYTES, strict_json_loads
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.service import (
    preflight_identity_authorization,
)

if TYPE_CHECKING:
    from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.service import (
        M0102Service,
    )

_REQUEST_ADAPTER: Final[TypeAdapter[ReconcileIdentityLineageRequest]] = TypeAdapter(
    ReconcileIdentityLineageRequest
)

_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M01-02",
    title="Identity and lineage reconciliation",
    version="1.0.0",
    owner="Computational biology",
    safety_class="S2",
    gate="G0",
    prohibited_outputs=(
        "direct or raw patient identity",
        "identity union inferred from tokens or concordance",
        "cross-patient lineage inference",
        "genotype or model scores",
        "treatment recommendation",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM0102Request:
    """Execution token carrying a request that passed the service preflight."""

    request: ReconcileIdentityLineageRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M01-02 execution requires a validated request token")


class M0102Plugin(
    ModulePlugin[object, ValidatedM0102Request, IdentityLineageResolution]
):
    """Expose strict parse, validate, and revalidated execution phases."""

    __slots__ = ("_service",)

    def __init__(self, service: M0102Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        """Return the immutable ownership and safety boundary."""

        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0102Request:
        """Parse bounded strict JSON, then run all fail-closed service checks."""

        candidate: object
        if isinstance(request, bytes | bytearray | str):
            decoded = strict_json_loads(request, max_bytes=MAX_JSON_BYTES)
            preflight_identity_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(request, strict=True)
        else:
            candidate = request
        validated = self._service.validate_request(candidate)
        return ValidatedM0102Request(request=validated)

    def run(self, request: ValidatedM0102Request) -> IdentityLineageResolution:
        """Execute through the service, which revalidates even a forged token."""

        if not isinstance(request, ValidatedM0102Request):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M0102Plugin", "ValidatedM0102Request"]
