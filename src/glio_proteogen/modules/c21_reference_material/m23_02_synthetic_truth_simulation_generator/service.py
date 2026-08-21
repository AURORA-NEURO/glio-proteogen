"""Typed service facade for M23-02."""

from __future__ import annotations

from typing import TYPE_CHECKING

from glio_proteogen.contracts.m23_02 import VariantPeptideSyntheticTruthResult

from .engine import M2302Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m23_02 import (
        GenerateVariantPeptideSyntheticTruthRequest,
    )


class M2302Service:
    """Stable service seam over the stateless M23-02 engine."""

    def __init__(self, engine: M2302Engine | None = None) -> None:
        self._engine = engine or M2302Engine()

    def validate_request(self, candidate: object) -> GenerateVariantPeptideSyntheticTruthRequest:
        return self._engine.validate_request(candidate)

    def execute(
        self, request: GenerateVariantPeptideSyntheticTruthRequest
    ) -> VariantPeptideSyntheticTruthResult:
        return self._engine.generate(request)

    def verify(
        self,
        result: object,
        request: GenerateVariantPeptideSyntheticTruthRequest | None = None,
    ) -> VariantPeptideSyntheticTruthResult:
        if request is not None:
            typed = (
                result
                if isinstance(result, VariantPeptideSyntheticTruthResult)
                else self._engine.replay(result)
            )
            result_request = typed.request.model_dump(mode="json")
            supplied_request = request.model_dump(mode="json")
            if result_request != supplied_request:
                raise ValueError
        return self._engine.replay(result)


__all__ = ["M2302Service"]
