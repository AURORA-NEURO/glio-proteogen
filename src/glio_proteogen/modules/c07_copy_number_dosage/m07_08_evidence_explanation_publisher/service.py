"""Stateless application boundary for provisional M07-08."""

from glio_proteogen.contracts.m07_08 import (
    ProteotypeEvidencePublicationResult,
    PublishProteotypeEvidenceRequest,
)

from .engine import M0708EvidencePublisherEngine, _prepare


class M0708Service:
    """Authorize, strictly validate, execute, and verify one M07-08 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0708EvidencePublisherEngine | None = None) -> None:
        self._engine = engine or M0708EvidencePublisherEngine()

    @staticmethod
    def validate_request(request: object) -> PublishProteotypeEvidenceRequest:
        return PublishProteotypeEvidenceRequest.model_validate(_prepare(request), strict=True)

    def _execute_validated(
        self,
        request: PublishProteotypeEvidenceRequest,
    ) -> ProteotypeEvidencePublicationResult:
        return self._engine.publish(request)

    def execute(self, request: object) -> ProteotypeEvidencePublicationResult:
        return self._engine.publish(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteotypeEvidencePublicationResult:
        """Verify a receipt and, by default, reconstruct its request transitively."""

        return self._engine.verify(result, replay=replay)


__all__ = ["M0708Service"]
