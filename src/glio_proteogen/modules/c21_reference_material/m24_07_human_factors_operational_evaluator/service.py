"""Typed service boundary for provisional M24-07 evaluation and replay."""

from __future__ import annotations

import json
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m24_07 import (
    M2407_MAX_CANONICAL_REQUEST_BYTES,
    BiomarkerPanelHumanFactorsResult,
    EvaluateBiomarkerPanelHumanFactorsRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import (
    M2407AuthorizationError,
    M2407HumanFactorsOperationalEvaluator,
    preflight_m2407_authorization,
)

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateBiomarkerPanelHumanFactorsRequest)


class M2407Service:
    """Strict-JSON service seam sharing one canonical evaluator."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2407HumanFactorsOperationalEvaluator | None = None) -> None:
        self._engine = engine or M2407HumanFactorsOperationalEvaluator()

    def validate_request(self, request: object) -> EvaluateBiomarkerPanelHumanFactorsRequest:
        try:
            if isinstance(request, bytes | bytearray | str):
                decoded = strict_json_loads(request, max_bytes=M2407_MAX_CANONICAL_REQUEST_BYTES)
                typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
            else:
                typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        except Exception as error:
            if isinstance(error, (ValueError, TypeError)):
                raise
            raise M2407AuthorizationError from None
        preflight_m2407_authorization(typed)
        return typed

    def evaluate(self, request: object) -> BiomarkerPanelHumanFactorsResult:
        return self._engine.evaluate(self.validate_request(request))

    def verify_replay(
        self,
        result: BiomarkerPanelHumanFactorsResult,
    ) -> BiomarkerPanelHumanFactorsResult:
        return self._engine.verify_replay(result)

    @staticmethod
    def export_json(result: BiomarkerPanelHumanFactorsResult) -> str:
        return json.dumps(result.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


__all__ = ["M2407Service"]
