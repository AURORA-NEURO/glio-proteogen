"""Stateless M08-01 service with explicit validate/execute/replay lifecycle."""

from glio_proteogen.contracts.m08_01 import (
    ValidateTranscriptProteinStateRequest,
    ValidateTranscriptProteinStateResult,
    canonical_request_digest,
)
from glio_proteogen.modules.c08_transcript_protein.m08_01_formal_state.engine import (
    M0801FormalStateEngine,
    _validate_typed_request,
    verify_m0801_result,
)


class M0801Service:
    """Validate once, execute immutably, and verify replayed results."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0801FormalStateEngine | None = None) -> None:
        self._engine = engine or M0801FormalStateEngine()

    @staticmethod
    def validate_request(request: object) -> ValidateTranscriptProteinStateRequest:
        return _validate_typed_request(request)

    def _execute_validated(
        self, request: ValidateTranscriptProteinStateRequest
    ) -> ValidateTranscriptProteinStateResult:
        return self._engine.validate_validated(request)

    def execute(self, request: object) -> ValidateTranscriptProteinStateResult:
        return self._execute_validated(self.validate_request(request))

    def verify(self, result: object) -> ValidateTranscriptProteinStateResult:
        return verify_m0801_result(result)

    def replay(
        self,
        request: object,
        result: object,
    ) -> ValidateTranscriptProteinStateResult:
        typed_request = self.validate_request(request)
        typed_result = self.verify(result)
        if typed_result.request_digest != canonical_request_digest(typed_request):
            raise ValueError("M08-01 replay request digest does not match")  # noqa: TRY003
        replayed = self._execute_validated(typed_request)
        if replayed.model_dump(mode="json") != typed_result.model_dump(mode="json"):
            raise ValueError("M08-01 replay result is not deterministic")  # noqa: TRY003
        return typed_result


__all__ = ["M0801Service"]
