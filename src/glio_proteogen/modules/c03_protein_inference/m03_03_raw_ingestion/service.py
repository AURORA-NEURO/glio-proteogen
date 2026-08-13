"""Stateless application boundary for M03-03 raw-source admission."""

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_03 import (
    IngestProteinInferenceRawInputsRequest,
    ProteinInferenceRawAdmissionResult,
)
from glio_proteogen.modules.c03_protein_inference.m03_03_raw_ingestion.engine import (
    M0303ProteinInferenceRawIngestionEngine,
    RawInputSource,
    preflight_protein_inference_raw_ingestion_authorization,
)

_REQUEST_ADAPTER: Final = TypeAdapter(IngestProteinInferenceRawInputsRequest)


class M0303Service:
    """Authorize and strictly validate before reading an exact source capsule."""

    __slots__ = ("_engine",)

    def __init__(
        self,
        engine: M0303ProteinInferenceRawIngestionEngine | None = None,
    ) -> None:
        self._engine = engine or M0303ProteinInferenceRawIngestionEngine()

    @staticmethod
    def validate_request(request: object) -> IngestProteinInferenceRawInputsRequest:
        preflight_protein_inference_raw_ingestion_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def execute(
        self,
        request: object,
        sources: Mapping[str, RawInputSource],
    ) -> ProteinInferenceRawAdmissionResult:
        return self._engine.ingest(request, sources)


__all__ = ["M0303Service"]
