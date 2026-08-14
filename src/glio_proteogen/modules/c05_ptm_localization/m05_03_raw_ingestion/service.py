"""Stateless application boundary for M05-03 raw-manifest ingestion."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from pydantic import TypeAdapter

from glio_proteogen.modules.c05_ptm_localization.m05_03_raw_ingestion.engine import (
    M0503PtmLocalizationRawInputIngester,
    _contracts,
    _plain_value,
    _PreparedPtmLocalizationRawInputs,
    _validate_outer_request_shape,
    preflight_ptm_localization_raw_input_authorization,
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
        preflight_ptm_localization_raw_input_authorization(request)
        contracts = _contracts()
        _validate_outer_request_shape(request, contracts)
        return cast(
            "IngestPtmLocalizationRawInputsRequest",
            TypeAdapter(
                cast("Any", contracts.IngestPtmLocalizationRawInputsRequest)
            ).validate_python(
                _plain_value(request),
                strict=True,
            ),
        )

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


__all__ = ["M0503Service"]
