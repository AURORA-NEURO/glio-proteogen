"""Bounded uncertainty kernel for provisional M08-06 execution."""

from __future__ import annotations

from glio_proteogen.contracts.m08_06 import (
    M0806_CONTRACT_VERSION,
    SensitivityEnvelope,
    SensitivityEnvelopeStatus,
    UncertaintyDecompositionPolicy,
)


class M0806UncertaintyKernel:
    """Keep sensitivity claims fail-closed until benchmark evidence is locked."""

    __slots__ = ()

    def sensitivity_envelope(
        self,
        policy: UncertaintyDecompositionPolicy,
    ) -> SensitivityEnvelope:
        return SensitivityEnvelope(
            status=SensitivityEnvelopeStatus.ABSTAINED,
            nominal_coverage=policy.nominal_coverage,
            rationale=(
                f"{M0806_CONTRACT_VERSION} has no owner-confirmed synthetic, internal, "
                "and external coverage evidence; no interval is emitted."
            ),
        )


__all__ = ["M0806UncertaintyKernel"]
