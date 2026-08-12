"""Agent-friendly validate-then-run boundary for M02-03."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m02_03 import (
    IdentificationRawIngestionResult,
    IngestIdentificationRawInputsRequest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import MAX_JSON_BYTES, strict_json_loads
from glio_proteogen.modules.c02_identification_qc.m02_03_raw_ingestion.engine import (
    preflight_identification_raw_ingestion_authorization,
    prepare_identification_raw_inputs,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from glio_proteogen.modules.c01_preanalytic.m01_03_raw_ingestion import RawInputSource
    from glio_proteogen.modules.c02_identification_qc.m02_03_raw_ingestion.service import (
        M0203Service,
    )

_REQUEST_ADAPTER: Final = TypeAdapter(IngestIdentificationRawInputsRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M02-03",
    title="Raw-format ingestion and parser",
    version="1.0.0",
    owner="ML engineering",
    safety_class="S2",
    gate="G0",
    prohibited_outputs=(
        "raw source retention or echo",
        "peptide, protein, subtype, or kinase inference",
        "upstream identity, consent, or provenance mutation",
        "missing or unsupported input interpreted as a negative finding",
    ),
)


@dataclass(frozen=True, slots=True)
class IdentificationRawIngestionSubmission:
    request: object
    sources: Mapping[str, RawInputSource]
    filenames: Mapping[str, str] | None = None


@dataclass(frozen=True, slots=True)
class ValidatedM0203Request:
    request: IngestIdentificationRawInputsRequest
    sources: Mapping[str, bytes]
    filenames: Mapping[str, str] | None


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M02-03 validation requires an ingestion submission")


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M02-03 execution requires a validated request token")


class M0203Plugin(
    ModulePlugin[object, ValidatedM0203Request, IdentificationRawIngestionResult]
):
    """Strict JSON request parsing plus ephemeral bounded source snapshots."""

    __slots__ = ("_service",)

    def __init__(self, service: M0203Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, submission: object) -> ValidatedM0203Request:
        if not isinstance(submission, IdentificationRawIngestionSubmission):
            raise _InvalidSubmissionError
        candidate = submission.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=MAX_JSON_BYTES)
            preflight_identification_raw_ingestion_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        request = self._service.validate_request(candidate)
        sources, filenames = prepare_identification_raw_inputs(
            request,
            submission.sources,
            submission.filenames,
        )
        return ValidatedM0203Request(
            request,
            sources,
            filenames if submission.filenames is not None else None,
        )

    def run(self, request: ValidatedM0203Request) -> IdentificationRawIngestionResult:
        if not isinstance(request, ValidatedM0203Request):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request, request.sources, request.filenames)


__all__ = [
    "IdentificationRawIngestionSubmission",
    "M0203Plugin",
    "ValidatedM0203Request",
]
