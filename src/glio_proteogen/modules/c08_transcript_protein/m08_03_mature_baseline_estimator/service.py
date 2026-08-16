"""M08-03 validate/estimate/replay service."""

from glio_proteogen.contracts.m08_03 import (
    EstimateProteinSubtypeBaselineRequest,
    ProteinSubtypeBaselineResult,
    canonical_request_digest,
)
from glio_proteogen.modules.c08_transcript_protein.m08_03_mature_baseline_estimator.engine import (
    M0803BaselineEngine,
    _validate_typed_request,
    verify_m0803_result,
)


class M0803Service:
    """Execute only validated baseline requests and verify deterministic replay."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0803BaselineEngine | None = None) -> None:
        self._engine = engine or M0803BaselineEngine()

    @staticmethod
    def validate_request(request: object) -> EstimateProteinSubtypeBaselineRequest:
        return _validate_typed_request(request)

    def _execute_validated(
        self, request: EstimateProteinSubtypeBaselineRequest
    ) -> ProteinSubtypeBaselineResult:
        return self._engine.estimate_validated(request)

    def execute(self, request: object) -> ProteinSubtypeBaselineResult:
        return self._execute_validated(self.validate_request(request))

    def verify(self, result: object) -> ProteinSubtypeBaselineResult:
        return verify_m0803_result(result)

    def replay(self, request: object, result: object) -> ProteinSubtypeBaselineResult:
        typed_request = self.validate_request(request)
        typed_result = self.verify(result)
        if typed_result.request_digest != canonical_request_digest(typed_request):
            raise ValueError("M08-03 replay request digest does not match")  # noqa: TRY003
        replayed = self._execute_validated(typed_request)
        if replayed.model_dump(mode="json") != typed_result.model_dump(mode="json"):
            raise ValueError("M08-03 replay result is not deterministic")  # noqa: TRY003
        return typed_result


__all__ = ["M0803Service"]
