"""Thin stateless M02-03 service."""

from collections.abc import Mapping

from pydantic import TypeAdapter

from glio_proteogen.contracts.m02_03 import (
    IdentificationRawIngestionResult,
    IngestIdentificationRawInputsRequest,
)
from glio_proteogen.modules.c01_preanalytic.m01_03_raw_ingestion import RawInputSource
from glio_proteogen.modules.c02_identification_qc.m02_03_raw_ingestion.engine import (
    M0203IdentificationRawIngestionEngine,
    preflight_identification_raw_ingestion_authorization,
)

_REQUEST_ADAPTER = TypeAdapter(IngestIdentificationRawInputsRequest)


class M0203Service:
    """Application boundary for identification raw ingestion."""

    def __init__(self) -> None:
        self._engine = M0203IdentificationRawIngestionEngine()

    def validate_request(self, request: object) -> IngestIdentificationRawInputsRequest:
        preflight_identification_raw_ingestion_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def execute(
        self,
        request: object,
        sources: Mapping[str, RawInputSource],
        filenames: Mapping[str, str] | None = None,
    ) -> IdentificationRawIngestionResult:
        return self._engine.evaluate(request, sources, filenames)


__all__ = ["M0203Service"]
