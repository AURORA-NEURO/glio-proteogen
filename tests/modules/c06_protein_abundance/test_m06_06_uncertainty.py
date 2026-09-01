"""Evidence-derived uncertainty decomposition tests for M06-06."""

from __future__ import annotations

from typing import TYPE_CHECKING

from glio_proteogen.contracts.m06_01 import FormalStateMissingness
from glio_proteogen.contracts.m06_06 import (
    DecomposeProteinAbundanceUncertaintyRequest,
    SensitivityEnvelopeStatus,
    UncertaintyDecompositionPolicy,
    UncertaintyDecompositionStatus,
    UncertaintyDimension,
)
from glio_proteogen.kernel.models import ArtifactReference
from glio_proteogen.modules.c06_protein_abundance.m06_05_mechanism_constraint_integrator import (
    M0605MechanismConstraintEngine,
)
from glio_proteogen.modules.c06_protein_abundance.m06_06_uncertainty_decomposition import (
    M0606UncertaintyDecompositionEngine,
)
from tests.modules.c06_protein_abundance.test_m06_05_constraint_integrator import _request

if TYPE_CHECKING:
    from glio_proteogen.contracts.m06_05 import IntegrateProteinAbundanceConstraintsRequest


def _artifact(label: str, digest_char: str = "f") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"evidence.m0606.{label}",
        version="1.0.0",
        digest=f"sha256:{digest_char * 64}",
        media_type="application/json",
    )


def _request_m0606(
    upstream_request: IntegrateProteinAbundanceConstraintsRequest | None = None,
) -> DecomposeProteinAbundanceUncertaintyRequest:
    source = upstream_request or _request()
    upstream = M0605MechanismConstraintEngine().integrate(source).result
    context = source.context.model_copy(update={"request_id": "request.m0606.test"})
    return DecomposeProteinAbundanceUncertaintyRequest(
        request_id="request.m0606.test",
        context=context,
        constraint_result=upstream,
        policy=UncertaintyDecompositionPolicy(
            policy_id="policy.m0606.test",
            version="1.0.0",
            method="locked-evidence-analytical",
            calibration_reference=_artifact("policy"),
        ),
        source_artifacts=(_artifact("source", "1"),),
    )


def test_m0606_decomposes_actual_constraint_evidence() -> None:
    result = M0606UncertaintyDecompositionEngine().decompose(_request_m0606())

    assert result.status is UncertaintyDecompositionStatus.DECOMPOSED
    assert result.decomposition is not None
    assert result.sensitivity_envelope.status is SensitivityEnvelopeStatus.EVALUATED
    assert {item.dimension for item in result.decomposition.components} == set(
        UncertaintyDimension
    )
    assert all(item.estimate.probability is not None for item in result.decomposition.components)
    assert result.human_review_required is False


def test_m0606_is_order_stable_and_policy_can_force_abstention() -> None:
    engine = M0606UncertaintyDecompositionEngine()
    first = engine.decompose(_request_m0606())
    second = engine.decompose(_request_m0606())
    assert first.result_digest == second.result_digest
    assert first.uncertainty == second.uncertainty

    unsafe = _request_m0606().model_copy(
        update={
            "policy": _request_m0606().policy.model_copy(
                update={"method": "uncalibrated-external-policy"}
            )
        }
    )
    abstained = engine.decompose(unsafe)
    assert abstained.status is UncertaintyDecompositionStatus.ABSTAINED
    assert abstained.decomposition is None
    assert abstained.sensitivity_envelope.status is SensitivityEnvelopeStatus.ABSTAINED


def test_m0606_preserves_upstream_abstention() -> None:
    result = M0606UncertaintyDecompositionEngine().decompose(
        _request_m0606(_request(state=FormalStateMissingness.MISSING))
    )
    assert result.status is UncertaintyDecompositionStatus.ABSTAINED
    assert result.decomposition is None
