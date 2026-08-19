"""Stateless application boundary for M04-02 identity-lineage reconciliation."""

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m04_02 import (
    M0402_MAX_CANONICAL_RESULT_BYTES,
    ProteoformIdentityLineageResolution,
    ReconcileProteoformIdentityLineageRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c04_proteoform_isoform.m04_02_identity_lineage.engine import (
    M0402ProteoformIdentityLineageReconciler,
    _plain_value,
    preflight_proteoform_identity_lineage_authorization,
)

_REQUEST_ADAPTER: Final = TypeAdapter(ReconcileProteoformIdentityLineageRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteoformIdentityLineageResolution)


class _ResultSizeError(ValueError):
    """Raised when a replay receipt exceeds the bounded M04-02 ingress."""

    def __init__(self) -> None:
        super().__init__("M04-02 result exceeds its canonical byte limit")


def _bounded_result_bytes(value: object) -> bytes:
    """Canonicalize every replay ingress shape under the result byte ceiling."""

    payload = canonical_json_bytes(value)
    if len(payload) > M0402_MAX_CANONICAL_RESULT_BYTES:
        raise _ResultSizeError
    return payload


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

    def verify(self, result: object) -> ProteoformIdentityLineageResolution:
        """Replay-verify one immutable result without reopening source evidence.

        The M04-02 result contract deterministically replays its embedded request,
        graph, findings, receipt, controls, and digest.  This boundary keeps API,
        CLI, and library callers on the same duplicate-safe, size-bounded path.
        """

        if isinstance(result, (bytes, bytearray, str)):
            decoded = strict_json_loads(
                result,
                max_bytes=M0402_MAX_CANONICAL_RESULT_BYTES,
            )
            return _RESULT_ADAPTER.validate_json(_bounded_result_bytes(decoded), strict=True)
        if isinstance(result, Mapping):
            return _RESULT_ADAPTER.validate_json(
                _bounded_result_bytes(dict(result)),
                strict=True,
            )
        return _RESULT_ADAPTER.validate_json(
            _bounded_result_bytes(result),
            strict=True,
        )


__all__ = ["M0402Service"]
