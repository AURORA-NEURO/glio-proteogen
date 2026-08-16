"""Application service boundary for M10-08."""

from glio_proteogen.contracts.m10_08 import (
    ProteinRnaEvidencePublicationResult,
    PublishProteinRnaEvidenceRequest,
)

from .engine import (
    M1008EvidencePublisherEngine,
    _validate_authorized_request,
    verify_publication_result,
)


class M1008EvidencePublisherService:
    """Validate, execute, and verify one immutable M10-08 publication."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1008EvidencePublisherEngine | None = None) -> None:
        self._engine = engine or M1008EvidencePublisherEngine()

    @staticmethod
    def validate_request(request: object) -> PublishProteinRnaEvidenceRequest:
        return _validate_authorized_request(request)

    def execute(self, request: object) -> ProteinRnaEvidencePublicationResult:
        return self._engine.publish(request)

    @staticmethod
    def verify(result: object) -> bool:
        return verify_publication_result(result)


__all__ = ["M1008EvidencePublisherService"]
