"""Stateless application boundary for provisional M06-08."""

from glio_proteogen.contracts.m06_08 import (
    ProteinAbundanceEvidencePublicationResult,
    PublishProteinAbundanceEvidenceRequest,
)

from .engine import (
    M0608EvidencePublisherEngine,
    _prepare,
)


class M0608Service:
    """Authorize, strictly validate, and execute one M06-08 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0608EvidencePublisherEngine | None = None) -> None:
        self._engine = engine or M0608EvidencePublisherEngine()

    @staticmethod
    def validate_request(request: object) -> PublishProteinAbundanceEvidenceRequest:
        return PublishProteinAbundanceEvidenceRequest.model_validate(_prepare(request), strict=True)

    def _execute_validated(
        self,
        request: PublishProteinAbundanceEvidenceRequest,
    ) -> ProteinAbundanceEvidencePublicationResult:
        return self._engine.publish(request)

    def execute(self, request: object) -> ProteinAbundanceEvidencePublicationResult:
        return self._engine.publish(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinAbundanceEvidencePublicationResult:
        """Verify a result receipt and optionally reconstruct the operation."""

        return self._engine.verify(result, replay=replay)


__all__ = ["M0608Service"]
