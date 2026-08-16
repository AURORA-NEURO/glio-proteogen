"""Strict validate-then-run plugin boundary for M06-01."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m06_01 import (
    M0601_MAX_CANONICAL_REQUEST_BYTES,
    ValidateFormalProteinStateRequest,
    ValidateFormalProteinStateResult,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c06_protein_abundance.m06_01_formal_state_schema.engine import (
    preflight_formal_state_authorization,
)

if TYPE_CHECKING:
    from glio_proteogen.modules.c06_protein_abundance.m06_01_formal_state_schema.service import (
        M0601Service,
    )

_REQUEST_ADAPTER: Final = TypeAdapter(ValidateFormalProteinStateRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M06-01",
    title="Formal state and feature schema",
    version="0.1.0-provisional",
    owner="Clinical science",
    safety_class="S2",
    gate="G0",
    prohibited_outputs=(
        "biomarker panel emission or clinical recommendation",
        "kinase-state ownership or generic all-omics fusion",
        "identity or consent inference and upstream evidence mutation",
    ),
)


@dataclass(frozen=True, slots=True)
class M0601Submission:
    request: object


@dataclass(frozen=True, slots=True)
class ValidatedM0601Request:
    """Opaque capability proving M06-01 accepted the request boundary."""

    request: ValidateFormalProteinStateRequest
    _seal: object


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M06-01 execution requires a validated request token")


class M0601Plugin:
    """Expose formal-state validation without widening scientific authority."""

    __slots__ = ("_service",)

    def __init__(self, service: M0601Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, submission: M0601Submission | object) -> ValidatedM0601Request:
        candidate = submission.request if isinstance(submission, M0601Submission) else submission
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=M0601_MAX_CANONICAL_REQUEST_BYTES)
            preflight_formal_state_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM0601Request(request=self._service.validate_request(candidate), _seal=self)

    def run(self, request: ValidatedM0601Request) -> ValidateFormalProteinStateResult:
        if not isinstance(request, ValidatedM0601Request) or request._seal is not self:
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M0601Plugin", "M0601Submission", "ValidatedM0601Request"]
