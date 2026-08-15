"""Focused import/schema/safety smoke for provisional M09-04."""

from typing import Final

import pytest

from glio_proteogen.contracts.m09_04 import (
    M0904_OUTPUT_MEDIA_TYPE,
    EstimateComplexActivityProbabilisticVerification,
    OptimizationDiagnostic,
    OptimizationDiagnosticStatus,
    PosteriorEstimate,
    PosteriorEstimateKind,
    ProbabilisticEstimatorConfiguration,
    ProbabilisticReplayReason,
    contract_json_schemas,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.modules.c09_complex_stoichiometry import (
    m09_04_probabilistic_estimator as runtime,
)
from tests.modules.c09_complex_stoichiometry.test_m09_04_estimator import _request

_SCHEMA_COUNT: Final = 8
_EXPECTED_CONTROLS: Final = 7


def test_provisional_schemas_are_strict_and_owner_pending() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M0904_OUTPUT_MEDIA_TYPE


def test_posterior_shape_and_preflight_fail_closed() -> None:
    posterior = PosteriorEstimate(
        feature_id="complex.posterior",
        kind=PosteriorEstimateKind.INTERVAL,
        unit="activity",
        estimate_value=0.5,
        lower_bound=0.2,
        upper_bound=0.8,
    )
    assert posterior.lower_bound <= posterior.estimate_value <= posterior.upper_bound
    with pytest.raises(runtime.M0904AuthorizationError):
        runtime.preflight_m0904_authorization({"context": {"references": {}}})
    assert runtime.M0904Plugin(runtime.M0904Service()).descriptor().module_id == (
        "GLIO-PROTEOGEN-M09-04"
    )


def test_schema_contract_closures_and_provenance_projection() -> None:
    request = _request("stable_support")
    digest = "sha256:" + ("1" * 64)
    provenance = expected_provenance(request, digest, digest)
    assert provenance.module_id == "GLIO-PROTEOGEN-M09-04"
    assert len(provenance.control_decisions) == _EXPECTED_CONTROLS

    with pytest.raises(ValueError, match="unique"):
        ProbabilisticEstimatorConfiguration.model_validate(
            request.configuration.model_dump(mode="python")
            | {"priors": (request.configuration.priors[0], request.configuration.priors[0])}
        )
    with pytest.raises(ValueError, match="unique"):
        ProbabilisticEstimatorConfiguration.model_validate(
            request.configuration.model_dump(mode="python")
            | {
                "constraints": (
                    request.configuration.constraints[0],
                    request.configuration.constraints[0],
                )
            }
        )

    with pytest.raises(ValueError, match="interval"):
        PosteriorEstimate(
            feature_id="feature.bad",
            kind=PosteriorEstimateKind.INTERVAL,
            unit="activity",
            estimate_value=0.5,
            lower_bound=0.8,
            upper_bound=0.9,
        )
    with pytest.raises(ValueError, match="scalar"):
        PosteriorEstimate(
            feature_id="feature.bad",
            kind=PosteriorEstimateKind.SCALAR,
            unit="activity",
        )
    with pytest.raises(ValueError, match="categorical"):
        PosteriorEstimate(
            feature_id="feature.bad",
            kind=PosteriorEstimateKind.CATEGORICAL,
            unit="class",
            estimate_value=0.5,
        )
    with pytest.raises(ValueError, match="objective value"):
        OptimizationDiagnostic(
            diagnostic_id="diagnostic.gap",
            status=OptimizationDiagnosticStatus.FAILED,
            objective="objective",
            iteration_count=0,
            objective_value=0.2,
            message="missing gap",
        )
    with pytest.raises(ValueError, match="verified"):
        EstimateComplexActivityProbabilisticVerification(
            content_verified=True,
            deterministic_verified=False,
            verified=True,
            result_digest=digest,
            reason=ProbabilisticReplayReason.VERIFIED,
        )
    with pytest.raises(ValueError, match="digest"):
        EstimateComplexActivityProbabilisticVerification(
            content_verified=False,
            deterministic_verified=False,
            verified=False,
            result_digest=digest,
            reason=ProbabilisticReplayReason.INVALID_RESULT,
        )
    assert expected_uncertainty().support.state.value == "not_estimable"
