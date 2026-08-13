"""Stateless application boundary for M03-02 artifact-lineage reconciliation."""

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_02.v1 import (
    ProteinInferenceIdentityLineageResolution,
    ReconcileProteinInferenceIdentityLineageRequest,
)
from glio_proteogen.modules.c03_protein_inference.m03_02_identity_lineage.engine import (
    M0302ProteinIdentityLineageReconciler,
    preflight_protein_identity_lineage_authorization,
)

_REQUEST_ADAPTER: Final = TypeAdapter(ReconcileProteinInferenceIdentityLineageRequest)


class M0302Service:
    """Authorize and strictly validate before reconciling the artifact DAG."""

    __slots__ = ("_reconciler",)

    def __init__(
        self,
        reconciler: M0302ProteinIdentityLineageReconciler | None = None,
    ) -> None:
        self._reconciler = reconciler or M0302ProteinIdentityLineageReconciler()

    @staticmethod
    def validate_request(request: object) -> ReconcileProteinInferenceIdentityLineageRequest:
        preflight_protein_identity_lineage_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def execute(self, request: object) -> ProteinInferenceIdentityLineageResolution:
        return self._reconciler.reconcile(request)


__all__ = ["M0302Service"]
