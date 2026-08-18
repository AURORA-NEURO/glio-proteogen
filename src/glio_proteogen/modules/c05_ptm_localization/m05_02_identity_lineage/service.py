"""Stateless application boundary for M05-02 identity-lineage reconciliation."""

from glio_proteogen.contracts.m05_02 import (
    PtmLocalizationIdentityLineageResolution,
    ReconcilePtmLocalizationIdentityLineageRequest,
)
from glio_proteogen.modules.c05_ptm_localization.m05_02_identity_lineage.engine import (
    M0502Engine,
    _prepare_request_candidate,
    _validate_prepared_request,
)


class M0502Service:
    """Authorize and strictly replay one identity-lineage request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0502Engine | None = None) -> None:
        self._engine = engine or M0502Engine()

    @staticmethod
    def validate_request(request: object) -> ReconcilePtmLocalizationIdentityLineageRequest:
        return _validate_prepared_request(_prepare_request_candidate(request))

    def _execute_validated(
        self,
        request: ReconcilePtmLocalizationIdentityLineageRequest,
    ) -> PtmLocalizationIdentityLineageResolution:
        return self._engine._reconcile_validated(request)

    def execute(self, request: object) -> PtmLocalizationIdentityLineageResolution:
        return self._engine.reconcile(request)


__all__ = ["M0502Service"]
