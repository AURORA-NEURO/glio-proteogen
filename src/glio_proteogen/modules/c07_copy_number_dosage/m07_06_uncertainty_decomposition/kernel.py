"""Bounded fail-closed kernel for provisional M07-06."""

from __future__ import annotations

from glio_proteogen.contracts.m07_06 import (
    M0706_CONTRACT_VERSION,
    SensitivityEnvelope,
    SensitivityEnvelopeStatus,
    UncertaintyDecompositionPolicy,
)


class M0706UncertaintyDecompositionKernel:
    """Never invent calibration; emit an explicit non-evaluable envelope."""

    __slots__ = ()

    def sensitivity_envelope(
        self,
        policy: UncertaintyDecompositionPolicy,
    ) -> SensitivityEnvelope:
        return SensitivityEnvelope(
            status=SensitivityEnvelopeStatus.ABSTAINED,
            nominal_coverage=policy.nominal_coverage,
            rationale=(
                f"{M0706_CONTRACT_VERSION} has no owner-confirmed benchmark coverage "
                "or calibration release; no interval is emitted."
            ),
        )


__all__ = ["M0706UncertaintyDecompositionKernel"]
