"""Adversarial runtime coverage for the provisional M10-04 estimator."""

import pytest
from pydantic import ValidationError

from evals.m10_04.run import build_request
from glio_proteogen.contracts.m10_04 import (
    EstimatorConstraint,
    OptimizationDiagnostic,
    OptimizationDiagnosticStatus,
    PosteriorEstimate,
    PosteriorEstimateKind,
    ProbabilisticEstimatorConfiguration,
    ProbabilisticPrior,
    ProbabilisticPriorKind,
)
from glio_proteogen.kernel.models import ControlRole, EstimateState, SupportStatus
from glio_proteogen.modules.c10_pathway_proteotype_factors.m10_04_probabilistic_advanced_estimator import (
    M1004ProbabilisticEstimatorAuthorizationError,
    M1004ProbabilisticEstimatorEngine,
    M1004Plugin,
    M1004ReplayVerificationError,
    M1004Service,
)


def test_estimator_publishes_safe_abstention_with_complete_controls() -> None:
    result = M1004Service().execute(build_request())
    assert result.status.value == "abstained"
    assert result.estimates == ()
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.human_review_required is True
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].status is OptimizationDiagnosticStatus.NOT_EVALUABLE
    assert result.uncertainty.measurement.state is EstimateState.NOT_ESTIMABLE
    assert len(result.provenance.control_decisions) == 7
    assert {item.role for item in result.evidence} == {"evidence"}
    assert result.emits_parent is False


def test_verify_can_skip_replay_but_still_checks_digest() -> None:
    service = M1004Service()
    result = service.execute(build_request())
    assert service.verify(result, replay=False).model_dump() == result.model_dump()
    with pytest.raises(M1004ReplayVerificationError):
        service.verify(result.model_copy(update={"abstention_reason": "changed"}), replay=False)


def test_unresolved_single_control_fails_closed() -> None:
    request = build_request()
    controls = request.context.references.model_copy(
        update={"support": request.context.references.support.model_copy(update={"state": "unknown"})}
    )
    blocked = request.model_copy(update={"context": request.context.model_copy(update={"references": controls})})
    with pytest.raises(M1004ProbabilisticEstimatorAuthorizationError):
        M1004Service().execute(blocked)


def test_plugin_requires_issued_parse_once_token() -> None:
    plugin = M1004Plugin(M1004Service())
    token = plugin.validate(build_request().model_dump_json())
    assert plugin.run(token).status.value == "abstained"
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]


def test_provenance_projects_every_declared_control_role() -> None:
    result = M1004ProbabilisticEstimatorEngine().estimate(build_request())
    roles = {item.role for item in result.provenance.control_decisions}
    assert roles == set(ControlRole)
    assert all(item.evidence_digest.startswith("sha256:") for item in result.provenance.control_decisions)


@pytest.mark.parametrize(
    ("kind", "values"),
    [
        (PosteriorEstimateKind.SCALAR, {"estimate_value": None}),
        (PosteriorEstimateKind.INTERVAL, {"estimate_value": 0.5, "lower_bound": 0.9, "upper_bound": 1.0}),
        (PosteriorEstimateKind.CATEGORICAL, {"category": None}),
    ],
)
def test_posterior_shape_rejects_incomplete_claims(kind: PosteriorEstimateKind, values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PosteriorEstimate(feature_id="feature.discordance", kind=kind, unit="probability", **values)


def test_converged_diagnostic_requires_objective_and_gap() -> None:
    with pytest.raises(ValidationError):
        OptimizationDiagnostic(
            diagnostic_id="diagnostic.invalid",
            status=OptimizationDiagnosticStatus.CONVERGED,
            objective="locked objective",
            iteration_count=1,
            message="missing convergence fields",
        )


def test_configuration_rejects_duplicate_prior_and_constraint_ids() -> None:
    prior = ProbabilisticPrior(
        prior_id="prior.duplicate",
        version="0.1.0",
        kind=ProbabilisticPriorKind.NORMAL,
        parameters=(0.0, 1.0),
    )
    with pytest.raises(ValidationError):
        ProbabilisticEstimatorConfiguration(
            configuration_id="configuration.invalid",
            version="0.1.0",
            estimator_family="probabilistic_learned",
            objective="locked objective",
            priors=(prior, prior),
            optimizer="deterministic",
            seed=1,
            max_iterations=2,
            reference=build_request().configuration.reference,
        )
    constraint = EstimatorConstraint(constraint_id="constraint.duplicate", expression="x >= 0", hard=True)
    with pytest.raises(ValidationError):
        ProbabilisticEstimatorConfiguration(
            configuration_id="configuration.invalid",
            version="0.1.0",
            estimator_family="probabilistic_learned",
            objective="locked objective",
            priors=(prior,),
            constraints=(constraint, constraint),
            optimizer="deterministic",
            seed=1,
            max_iterations=2,
            reference=build_request().configuration.reference,
        )
