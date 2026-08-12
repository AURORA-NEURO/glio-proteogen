"""Agent-friendly validate-then-run boundary for M01-03."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_03 import IngestRawInputsRequest, RawIngestionResult
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import MAX_JSON_BYTES, strict_json_loads
from glio_proteogen.modules.c01_preanalytic.m01_03_raw_ingestion.service import (
    M0103Service,
    RawInputSource,
    _prepare_inputs,
    preflight_raw_ingestion_authorization,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

_REQUEST_ADAPTER: Final[TypeAdapter[IngestRawInputsRequest]] = TypeAdapter(
    IngestRawInputsRequest
)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M01-03",
    title="Raw-format ingestion and parser",
    version="1.0.0",
    owner="Bioinformatics",
    safety_class="S2",
    gate="G0",
    prohibited_outputs=(
        "raw source retention or echo",
        "upstream identity, consent, or provenance mutation",
        "missing input interpreted as a negative finding",
        "molecular-state or treatment recommendation",
    ),
)


@dataclass(frozen=True, slots=True)
class RawIngestionSubmission:
    """Caller-owned request and source handles presented to the plugin."""

    request: object
    sources: Mapping[str, RawInputSource]
    filenames: Mapping[str, str] | None = None


@dataclass(frozen=True, slots=True)
class ValidatedM0103Request:
    """Ephemeral execution token with immutable batch membership."""

    request: IngestRawInputsRequest
    sources: Mapping[str, RawInputSource]
    filenames: Mapping[str, str]


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M01-03 validation requires a raw-ingestion submission")


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M01-03 execution requires a validated request token")


class M0103Plugin(ModulePlugin[object, ValidatedM0103Request, RawIngestionResult]):
    """Expose strict request parsing, bounded batch validation, and revalidated execution."""

    __slots__ = ("_service",)

    def __init__(self, service: M0103Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        """Return the immutable ownership and safety boundary."""

        return _DESCRIPTOR

    def validate(self, submission: object) -> ValidatedM0103Request:
        """Authorize the request, then snapshot and bound source-map membership."""

        if not isinstance(submission, RawIngestionSubmission):
            raise _InvalidSubmissionError
        candidate = submission.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=MAX_JSON_BYTES)
            preflight_raw_ingestion_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        request = self._service.validate_request(candidate)
        sources, filenames = _prepare_inputs(
            request,
            submission.sources,
            submission.filenames,
        )
        return ValidatedM0103Request(
            request=request,
            sources=sources,
            filenames=filenames,
        )

    def run(self, request: ValidatedM0103Request) -> RawIngestionResult:
        """Execute through the service, revalidating even a forged token."""

        if not isinstance(request, ValidatedM0103Request):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request, request.sources, request.filenames)


__all__ = [
    "M0103Plugin",
    "RawIngestionSubmission",
    "ValidatedM0103Request",
]
