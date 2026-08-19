"""Strict service seam for provisional M21-07 evaluation."""

from __future__ import annotations

from collections.abc import Mapping

from glio_proteogen.contracts.m21_07 import (
    ComplexActivityHumanFactorsResult,
    EvaluateComplexActivityHumanFactorsRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M2107Engine, preflight_m2107_authorization


class M2107Service:
    """Parse once, evaluate deterministically, and replay exact results."""

    def __init__(self, engine: M2107Engine | None = None) -> None:
        self._engine = engine or M2107Engine()

    def validate_request(self, request: object) -> EvaluateComplexActivityHumanFactorsRequest:
        preflight_m2107_authorization(request)
        return EvaluateComplexActivityHumanFactorsRequest.model_validate(request, strict=True)

    def evaluate(self, request: object) -> ComplexActivityHumanFactorsResult:
        if isinstance(request, (bytes, bytearray, str)):
            parsed = strict_json_loads(request, max_bytes=4 * 1024 * 1024)
            request = EvaluateComplexActivityHumanFactorsRequest.model_validate_json(
                canonical_json_bytes(parsed), strict=True
            )
        elif isinstance(request, Mapping):
            request = EvaluateComplexActivityHumanFactorsRequest.model_validate_json(
                canonical_json_bytes(dict(request)), strict=True
            )
        return self._engine.evaluate(request)

    def replay(self, result: object) -> ComplexActivityHumanFactorsResult:
        if isinstance(result, (bytes, bytearray, str)):
            parsed = strict_json_loads(result, max_bytes=8 * 1024 * 1024)
            result = ComplexActivityHumanFactorsResult.model_validate_json(
                canonical_json_bytes(parsed), strict=True
            )
        elif isinstance(result, Mapping):
            result = ComplexActivityHumanFactorsResult.model_validate_json(
                canonical_json_bytes(dict(result)), strict=True
            )
        else:
            result = ComplexActivityHumanFactorsResult.model_validate(result, strict=True)
        return self._engine.replay(result)

    @property
    def descriptor(self) -> dict[str, object]:
        return {
            "module_id": "GLIO-PROTEOGEN-M21-07",
            "operation": "evaluate_complex_activity_human_factors",
            "owner": "Bioinformatics",
            "safety_class": "S3",
            "gate": "G4",
            "parent": "complex activity",
            "upstream_media_type": "application/vnd.glio-proteogen.m21-06+json",
            "provisional_abi": True,
            "unsupported_to_negative": False,
            "human_review_required": True,
            "prohibited_outputs": (
                "complex-activity estimate",
                "kinase activity",
                "generic all-omics fusion",
                "treatment recommendation",
                "identity inference",
                "consent inference",
            ),
        }


__all__ = ["M2107Service"]
