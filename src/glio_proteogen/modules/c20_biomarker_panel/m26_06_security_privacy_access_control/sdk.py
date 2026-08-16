"""Typed SDK facade preserving the M26-06 service boundary."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .service import M2606SecurityService

if TYPE_CHECKING:
    from glio_proteogen.contracts.m26_06 import (
        EvaluateProteomicsSecurityAccessRequest,
        ProteomicsSecurityAccessResult,
    )


class M2606SecurityClient:
    """Small typed client with no authority or replay bypass."""

    __slots__ = ("_service",)

    def __init__(self, service: M2606SecurityService | None = None) -> None:
        self._service = service or M2606SecurityService()

    def validate(self, request: object) -> EvaluateProteomicsSecurityAccessRequest:
        return self._service.validate_request(request)

    def evaluate(self, request: object) -> ProteomicsSecurityAccessResult:
        return self._service.execute(request)

    def verify(self, result: object) -> ProteomicsSecurityAccessResult:
        return self._service.verify(result)

    def evaluate_json(self, request: object) -> dict[str, Any]:
        return self.evaluate(request).model_dump(mode="json")


__all__ = ["M2606SecurityClient"]
