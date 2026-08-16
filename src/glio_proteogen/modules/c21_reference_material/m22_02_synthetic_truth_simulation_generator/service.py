"""Service boundary for provisional M22-02 generation and replay."""

from __future__ import annotations

import json

from glio_proteogen.contracts.m22_02.v1 import (
    GenerateProteinRnaDiscordanceSyntheticTruthRequest,
    ProteinRnaDiscordanceSyntheticTruthResult,
)
from glio_proteogen.modules.c21_reference_material.m22_02_synthetic_truth_simulation_generator.engine import (  # noqa: E501
    M2202SyntheticTruthGenerator,
)


class M2202Service:
    """Typed and strict-JSON service seam sharing one canonical engine."""

    def __init__(self) -> None:
        self._engine = M2202SyntheticTruthGenerator()

    def validate_request(
        self,
        request: object,
    ) -> GenerateProteinRnaDiscordanceSyntheticTruthRequest:
        if isinstance(request, str):
            return GenerateProteinRnaDiscordanceSyntheticTruthRequest.model_validate_json(
                request, strict=True
            )
        return GenerateProteinRnaDiscordanceSyntheticTruthRequest.model_validate(
            request, strict=True
        )

    def generate(self, request: object) -> ProteinRnaDiscordanceSyntheticTruthResult:
        return self._engine.generate(self.validate_request(request))

    def verify_replay(
        self,
        result: ProteinRnaDiscordanceSyntheticTruthResult,
    ) -> ProteinRnaDiscordanceSyntheticTruthResult:
        return self._engine.verify_replay(result)

    @staticmethod
    def export_json(result: ProteinRnaDiscordanceSyntheticTruthResult) -> str:
        return json.dumps(result.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


__all__ = ["M2202Service"]
