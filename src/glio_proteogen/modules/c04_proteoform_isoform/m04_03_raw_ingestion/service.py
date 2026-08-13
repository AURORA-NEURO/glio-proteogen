"""Stateless application boundary for M04-03 raw-manifest ingestion."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from pydantic import TypeAdapter

from glio_proteogen.modules.c04_proteoform_isoform.m04_03_raw_ingestion.engine import (
    M0403ProteoformRawInputIngester,
    _contracts,
    _plain_value,
    _PreparedProteoformRawInputs,
    preflight_proteoform_raw_input_authorization,
)

if TYPE_CHECKING:
    from glio_proteogen.contracts.m04_03 import (
        IngestProteoformRawInputsRequest,
        ProteoformRawInputValidationResult,
    )


class M0403Service:
    """Authorize and strictly validate before manifest-byte access."""

    __slots__ = ("_ingester",)

    def __init__(self, ingester: M0403ProteoformRawInputIngester | None = None) -> None:
        self._ingester = ingester or M0403ProteoformRawInputIngester()

    @staticmethod
    def validate_request(request: object) -> IngestProteoformRawInputsRequest:
        preflight_proteoform_raw_input_authorization(request)
        contracts = _contracts()
        return cast(
            "IngestProteoformRawInputsRequest",
            TypeAdapter(cast("Any", contracts.IngestProteoformRawInputsRequest)).validate_python(
                _plain_value(request),
                strict=True,
            ),
        )

    def execute(
        self,
        request: object,
        artifacts_by_role: object,
    ) -> ProteoformRawInputValidationResult:
        return self._ingester.ingest(request, artifacts_by_role)

    def _execute_prepared(
        self,
        request: IngestProteoformRawInputsRequest,
        prepared: _PreparedProteoformRawInputs,
    ) -> ProteoformRawInputValidationResult:
        """Consume a private once-read capability without revisiting caller data."""

        return self._ingester._ingest_prepared(request, prepared)


__all__ = ["M0403Service"]
