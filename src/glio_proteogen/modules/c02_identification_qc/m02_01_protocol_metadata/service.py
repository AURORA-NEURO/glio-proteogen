"""Thin stateless M02-01 conformance service."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m02_01 import (
    ConformanceEvaluation,
    EvaluateConformanceRequest,
)
from glio_proteogen.modules.c02_identification_qc.m02_01_protocol_metadata.engine import (
    M0201ConformanceEvaluator,
    preflight_conformance_authorization,
)

_REQUEST_ADAPTER: Final[TypeAdapter[EvaluateConformanceRequest]] = TypeAdapter(
    EvaluateConformanceRequest
)


class M0201Service:
    """Preflight, strictly revalidate, and evaluate one request."""

    __slots__ = ("_evaluator",)

    def __init__(self, evaluator: M0201ConformanceEvaluator | None = None) -> None:
        self._evaluator = evaluator or M0201ConformanceEvaluator()

    @staticmethod
    def validate_request(request: object) -> EvaluateConformanceRequest:
        preflight_conformance_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def execute(self, request: object) -> ConformanceEvaluation:
        return self._evaluator.evaluate(self.validate_request(request))


__all__ = ["M0201Service"]
