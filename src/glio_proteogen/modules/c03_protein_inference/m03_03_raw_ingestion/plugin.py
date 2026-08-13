"""Strict validate-then-run plugin boundary for M03-03."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_03 import (
    M0303_MAX_CANONICAL_REQUEST_BYTES,
    IngestProteinInferenceRawInputsRequest,
    ProteinInferenceRawAdmissionResult,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c03_protein_inference.m03_03_raw_ingestion.engine import (
    RawInputSource,
    preflight_protein_inference_raw_ingestion_authorization,
    prepare_protein_inference_raw_inputs,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from glio_proteogen.modules.c03_protein_inference.m03_03_raw_ingestion.service import (
        M0303Service,
    )

_REQUEST_ADAPTER: Final = TypeAdapter(IngestProteinInferenceRawInputsRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M03-03",
    title="Raw-format ingestion and parser",
    version="1.0.0",
    owner="Quality engineering",
    safety_class="S2",
    gate="G0",
    prohibited_outputs=(
        "raw source bytes, identifiers, accessions, sequences, or measurements",
        "protein, proteoform, abundance, complex-activity, subtype, or proteotype inference",
        "kinase-state inference, generic omics fusion, treatment, or clinical recommendation",
        "upstream identity mutation, relabeling, disagreement erasure, or missing-as-negative use",
    ),
)


@dataclass(frozen=True, slots=True)
class ProteinInferenceRawIngestionSubmission:
    """Metadata request plus separately supplied caller-owned byte sources."""

    request: object
    sources: Mapping[str, RawInputSource]


@dataclass(frozen=True, slots=True)
class ValidatedM0303Request:
    """Opaque capability containing immutable read-once source snapshots."""

    request: IngestProteinInferenceRawInputsRequest
    sources: Mapping[str, bytes]


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M03-03 validation requires a raw-ingestion submission")


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M03-03 execution requires a validated request token")


class M0303Plugin(ModulePlugin[object, ValidatedM0303Request, ProteinInferenceRawAdmissionResult]):
    """Parse strict metadata and grant one immutable snapshot capability."""

    __slots__ = ("_service",)

    def __init__(self, service: M0303Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, submission: object) -> ValidatedM0303Request:
        if not isinstance(submission, ProteinInferenceRawIngestionSubmission):
            raise _InvalidSubmissionError
        candidate = submission.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(
                candidate,
                max_bytes=M0303_MAX_CANONICAL_REQUEST_BYTES,
            )
            preflight_protein_inference_raw_ingestion_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        request = self._service.validate_request(candidate)
        # Safe-failure requests are contract-closed with zero declarations. Preparing that empty
        # set would still iterate a hostile mapping, so preserve the authorization-first guarantee.
        if not request.sources:
            snapshots: Mapping[str, bytes] = MappingProxyType({})
        else:
            snapshots = prepare_protein_inference_raw_inputs(request, submission.sources)
        return ValidatedM0303Request(request=request, sources=snapshots)

    def run(self, request: ValidatedM0303Request) -> ProteinInferenceRawAdmissionResult:
        if not isinstance(request, ValidatedM0303Request):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request, request.sources)


__all__ = [
    "M0303Plugin",
    "ProteinInferenceRawIngestionSubmission",
    "ValidatedM0303Request",
]
