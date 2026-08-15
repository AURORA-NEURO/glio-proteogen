"""Descriptor-only plugin seam for the provisional M05-08 package boundary."""

from __future__ import annotations

from typing import Final

from glio_proteogen.contracts.m05_08 import M0508_CONTRACT_VERSION, M0508_MODULE_ID
from glio_proteogen.modules.c05_ptm_localization.m05_08_release_packaging.service import M0508Service

_PROVISIONAL_DESCRIPTOR: Final = {
    "moduleId": M0508_MODULE_ID,
    "title": "PTM-localization provenance and release packaging",
    "version": M0508_CONTRACT_VERSION,
    "status": "provisional",
    "prohibitedOutputs": (
        "kinase_activity",
        "all_omics_fusion",
        "treatment_recommendation",
        "identity_inference",
    ),
}


class M0508Plugin:
    """Minimal plugin seam; token sealing is deferred until the ABI is frozen."""

    descriptor = _PROVISIONAL_DESCRIPTOR

    def __init__(self) -> None:
        self._service = M0508Service()

    def validate_request(self, request: object) -> object:
        return self._service.validate_request(request)

    def execute(self, request: object) -> None:
        return self._service.execute(request)


__all__ = ["M0508Plugin"]
