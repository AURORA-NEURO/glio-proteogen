"""Focused schema and probabilistic-estimator smoke for provisional M10-04."""

from typing import cast

from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m10_04 import (
    M1004_BASELINE_MEDIA_TYPE,
    M1004_OUTPUT_MEDIA_TYPE,
    EstimatorConstraint,
    OptimizationDiagnostic,
    OptimizationDiagnosticStatus,
    ProbabilisticEstimatorConfiguration,
    ProbabilisticEstimatorFamily,
    ProbabilisticPrior,
    ProbabilisticPriorKind,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference

_DIGEST = "sha256:" + ("a" * 64)
_SEED = 17


def _artifact(name: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="0.1.0",
        digest=_DIGEST,
        media_type="application/json",
    )


def test_schema_inventory_is_strict_and_provisional() -> None:
    schemas = contract_json_schemas()
    assert tuple(schemas) == (
        "request",
        "output",
        "posterior",
        "diagnostic",
        "prior",
        "constraint",
        "configuration",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert metadata["provisionalAbi"] is True
        assert metadata["preregisteredObjectiveRequired"] is True
        assert metadata["deterministicSeedRequired"] is True
        assert metadata["priorsAndConstraintsDeclared"] is True
        assert metadata["optimizationDiagnosticsRequired"] is True
        assert metadata["failureHandlingExplicit"] is True
        assert metadata["unsupportedToNegative"] is False
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1004_OUTPUT_MEDIA_TYPE
    assert schemas["request"]["x-glio-contract"]["baselineInputMediaType"] == (
        M1004_BASELINE_MEDIA_TYPE
    )


def test_locked_configuration_and_diagnostic_smoke() -> None:
    prior = ProbabilisticPrior(
        prior_id="prior.m1004.smoke",
        version="0.1.0",
        kind=ProbabilisticPriorKind.NORMAL,
        parameters=(0.0, 1.0),
    )
    constraint = EstimatorConstraint(
        constraint_id="constraint.m1004.smoke",
        expression="posterior variance >= 0",
        hard=True,
    )
    configuration = ProbabilisticEstimatorConfiguration(
        configuration_id="configuration.m1004.smoke",
        version="0.1.0",
        estimator_family=ProbabilisticEstimatorFamily.STRUCTURE_AWARE,
        objective="locked baseline improvement",
        priors=(prior,),
        constraints=(constraint,),
        optimizer="deterministic-lbfgs",
        seed=_SEED,
        max_iterations=100,
        reference=_artifact("artifact.model"),
    )
    diagnostic = OptimizationDiagnostic(
        diagnostic_id="diagnostic.m1004.smoke",
        status=OptimizationDiagnosticStatus.CONVERGED,
        objective="locked baseline improvement",
        iteration_count=12,
        objective_value=0.2,
        convergence_gap=0.001,
        message="Optimization converged in the provisional fixture.",
    )
    assert configuration.locked is True
    assert configuration.seed == _SEED
    assert diagnostic.status is OptimizationDiagnosticStatus.CONVERGED
