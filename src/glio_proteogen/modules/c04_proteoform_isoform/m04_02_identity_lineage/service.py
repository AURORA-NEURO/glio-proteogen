"""Stateless application boundary for M04-02 identity-lineage reconciliation."""

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m04_02 import (
    ProteoformIdentityLineageResolution,
    ReconcileProteoformIdentityLineageRequest,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_02_identity_lineage.engine import (
    M0402ProteoformIdentityLineageReconciler,
    _plain_value,
    preflight_proteoform_identity_lineage_authorization,
)

_REQUEST_ADAPTER: Final = TypeAdapter(ReconcileProteoformIdentityLineageRequest)


class M0402Service:
    """Authorize and strictly validate before deterministic reconciliation."""

    __slots__ = ("_reconciler",)

    def __init__(
        self,
        reconciler: M0402ProteoformIdentityLineageReconciler | None = None,
    ) -> None:
        self._reconciler = reconciler or M0402ProteoformIdentityLineageReconciler()

    @staticmethod
    def validate_request(request: object) -> ReconcileProteoformIdentityLineageRequest:
        preflight_proteoform_identity_lineage_authorization(request)
        return _REQUEST_ADAPTER.validate_python(_plain_value(request), strict=True)

    def execute(self, request: object) -> ProteoformIdentityLineageResolution:
        return self._reconciler.reconcile(request)


__all__ = ["M0402Service"]
