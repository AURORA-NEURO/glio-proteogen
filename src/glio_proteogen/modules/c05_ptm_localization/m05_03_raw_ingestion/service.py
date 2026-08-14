"""Stateless application boundary for M05-03 raw-manifest ingestion."""

from __future__ import annotations

from typing import TYPE_CHECKING

from glio_proteogen.modules.c05_ptm_localization.m05_03_raw_ingestion.engine import (
    M0503PtmLocalizationRawInputIngester,
    _prepare_ptm_localization_raw_inputs,
    _PreparedPtmLocalizationRawInputs,
    _validate_request_candidate,
)

if TYPE_CHECKING:
    from glio_proteogen.contracts.m05_03 import (
        IngestPtmLocalizationRawInputsRequest,
        PtmLocalizationRawInputValidationResult,
    )


class M0503Service:
    """Authorize and strictly validate before manifest-byte access."""

    __slots__ = ("_ingester",)

    def __init__(self, ingester: M0503PtmLocalizationRawInputIngester | None = None) -> None:
        self._ingester = ingester or M0503PtmLocalizationRawInputIngester()

    @staticmethod
    def validate_request(request: object) -> IngestPtmLocalizationRawInputsRequest:
        return _validate_request_candidate(request)

    def execute(
        self,
        request: object,
        artifacts_by_role: object,
    ) -> PtmLocalizationRawInputValidationResult:
        return self._ingester.ingest(request, artifacts_by_role)

    def _execute_prepared(
        self,
        request: IngestPtmLocalizationRawInputsRequest,
        prepared: _PreparedPtmLocalizationRawInputs,
    ) -> PtmLocalizationRawInputValidationResult:
        """Consume a private once-read capability without revisiting caller data."""

        return self._ingester._ingest_prepared(request, prepared)

    def _execute_validated(
        self,
        request: IngestPtmLocalizationRawInputsRequest,
        artifacts_by_role: object,
    ) -> PtmLocalizationRawInputValidationResult:
        """Consume an adapter-validated request without replaying its JSON boundary."""

        prepared = (
            _prepare_ptm_localization_raw_inputs(request, artifacts_by_role)
            if request.lineage_result.disposition.value == "reconciled"
            else _PreparedPtmLocalizationRawInputs(snapshots=(), documents=())
        )
        return self._execute_prepared(request, prepared)


__all__ = ["M0503Service"]
