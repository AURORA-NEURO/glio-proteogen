"""Service boundary for provisional M24-05 evaluation and replay."""

from __future__ import annotations

import json
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m24_05 import (
    BiomarkerPanelSubgroupEvaluationResult,
    EvaluateBiomarkerPanelSubgroupEquityRequest,
)

from .engine import (
    M2405AuthorizationError,
    M2405SubgroupEquityEvaluator,
    preflight_m2405_authorization,
)

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateBiomarkerPanelSubgroupEquityRequest)


class M2405Service:
    """Typed and strict-JSON service seam sharing one canonical evaluator."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2405SubgroupEquityEvaluator | None = None) -> None:
        self._engine = engine or M2405SubgroupEquityEvaluator()

    def validate_request(self, request: object) -> EvaluateBiomarkerPanelSubgroupEquityRequest:
        try:
            if isinstance(request, bytes | bytearray | str):
                typed = _REQUEST_ADAPTER.validate_json(request, strict=True)
            else:
                typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        except Exception as error:
            if isinstance(error, (ValueError, TypeError)):
                raise
            raise M2405AuthorizationError from None
        preflight_m2405_authorization(typed)
        return typed

    def evaluate(self, request: object) -> BiomarkerPanelSubgroupEvaluationResult:
        return self._engine.evaluate(self.validate_request(request))

    def verify_replay(
        self,
        result: BiomarkerPanelSubgroupEvaluationResult,
    ) -> BiomarkerPanelSubgroupEvaluationResult:
        return self._engine.verify_replay(result)

    @staticmethod
    def export_json(result: BiomarkerPanelSubgroupEvaluationResult) -> str:
        return json.dumps(result.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


__all__ = ["M2405Service"]
