"""Adversarial runtime coverage for the provisional M10-04 estimator."""

# Test status codes and dossier control counts are intentionally literal.
# ruff: noqa: PLR2004

import pytest
from evals.m10_04.run import build_request
from pydantic import ValidationError

from glio_proteogen.contracts.m10_04 import (
    EstimatorConstraint,
    OptimizationDiagnostic,
    OptimizationDiagnosticStatus,
    PosteriorEstimate,
    PosteriorEstimateKind,
    ProbabilisticEstimatorConfiguration,
    ProbabilisticEstimatorFamily,
    ProbabilisticPrior,
    ProbabilisticPriorKind,
    ProbabilisticResultStatus,
)
from glio_proteogen.contracts.m10_04.canonical import result_payload_digest, verify_result_digest
from glio_proteogen.kernel.models import (
    ControlRole,
    EstimateState,
    EvidenceReference,
    SupportDecision,
    SupportStatus,
)
from glio_proteogen.modules.c10_pathway_proteotype_factors.m10_04_probabilistic_advanced_estimator import (  # noqa: E501
    M1004Plugin,
    M1004ProbabilisticEstimatorAuthorizationError,
    M1004ProbabilisticEstimatorEngine,
    M1004ReplayVerificationError,
    M1004Service,
    estimate_protein_rna_discordance_probabilistic,
    preflight_probabilistic_estimator_authorization,
)
from glio_proteogen.modules.c10_pathway_proteotype_factors.m10_04_probabilistic_advanced_estimator.plugin import (  # noqa: E501
    ValidatedM1004Request,
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
        update={
            "support": request.context.references.support.model_copy(update={"state": "unknown"})
        }
    )
    blocked = request.model_copy(
        update={"context": request.context.model_copy(update={"references": controls})}
    )
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
    assert all(
        item.evidence_digest.startswith("sha256:") for item in result.provenance.control_decisions
    )


@pytest.mark.parametrize(
    ("kind", "values"),
    [
        (PosteriorEstimateKind.SCALAR, {"estimate_value": None}),
        (
            PosteriorEstimateKind.INTERVAL,
            {"estimate_value": 0.5, "lower_bound": 0.9, "upper_bound": 1.0},
        ),
        (PosteriorEstimateKind.CATEGORICAL, {"category": None}),
    ],
)
def test_posterior_shape_rejects_incomplete_claims(
    kind: PosteriorEstimateKind, values: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        PosteriorEstimate(feature_id="feature.discordance", kind=kind, unit="probability", **values)


def test_posterior_scalar_interval_and_category_valid_shapes() -> None:
    assert (
        PosteriorEstimate(
            feature_id="feature.scalar",
            kind=PosteriorEstimateKind.SCALAR,
            unit="probability",
            estimate_value=0.5,
        ).estimate_value
        == 0.5
    )
    assert (
        PosteriorEstimate(
            feature_id="feature.interval",
            kind=PosteriorEstimateKind.INTERVAL,
            unit="probability",
            estimate_value=0.5,
            lower_bound=0.2,
            upper_bound=0.8,
        ).upper_bound
        == 0.8
    )
    assert (
        PosteriorEstimate(
            feature_id="feature.category",
            kind=PosteriorEstimateKind.CATEGORICAL,
            unit="class",
            category="discordant",
        ).category
        == "discordant"
    )


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
    constraint = EstimatorConstraint(
        constraint_id="constraint.duplicate", expression="x >= 0", hard=True
    )
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


def test_public_operation_and_mapping_preflight_are_deterministic() -> None:
    request = build_request()
    result = estimate_protein_rna_discordance_probabilistic(request)
    assert result.request.request_id == request.request_id
    preflight_probabilistic_estimator_authorization(request.model_dump(mode="python"))


def test_hostile_preflight_object_fails_closed() -> None:
    class Hostile:
        @property
        def context(self) -> object:
            raise RuntimeError("hostile")

    with pytest.raises(M1004ProbabilisticEstimatorAuthorizationError):
        preflight_probabilistic_estimator_authorization(Hostile())


def test_plugin_descriptor_nonserialized_validation_and_verification() -> None:
    plugin = M1004Plugin(M1004Service())
    request = build_request()
    token = plugin.validate(request)
    result = plugin.run(token)
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M10-04"
    assert plugin.verify(result).result_id == result.result_id
    forged = ValidatedM1004Request(request=request, _seal=object())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)


def test_engine_rejects_malformed_and_non_model_receipts() -> None:
    engine = M1004ProbabilisticEstimatorEngine()
    with pytest.raises(M1004ReplayVerificationError):
        engine.verify({"result_digest": "not-a-digest"})
    result = engine.estimate(build_request())
    assert verify_result_digest(result) is True
    assert verify_result_digest({}) is False
    with pytest.raises(M1004ReplayVerificationError):
        engine.verify(result.model_copy(update={"request_digest": "sha256:" + "0" * 64}))
    embedded_mismatch = result.model_copy(update={"request_digest": "sha256:" + "0" * 64})
    embedded_mismatch = embedded_mismatch.model_copy(
        update={"result_digest": result_payload_digest(embedded_mismatch)}
    )
    with pytest.raises(M1004ReplayVerificationError):
        engine.verify(embedded_mismatch)
    payload_mismatch = result.model_dump(mode="python")
    payload_mismatch["result_digest"] = "sha256:" + "1" * 64
    with pytest.raises(M1004ReplayVerificationError):
        engine.verify(payload_mismatch, replay=False)
    replay_mismatch = result.model_copy(update={"abstention_reason": "changed"})
    replay_mismatch = replay_mismatch.model_copy(
        update={"result_digest": result_payload_digest(replay_mismatch)}
    )
    with pytest.raises(M1004ReplayVerificationError):
        engine.verify(replay_mismatch)


def test_wrong_role_evidence_is_rejected_across_contract_objects() -> None:
    request = build_request()
    reference = EvidenceReference(
        reference=request.configuration.reference,
        role="counter_evidence",
        claim="counter-evidence fixture",
    )
    with pytest.raises(ValidationError):
        ProbabilisticPrior(
            prior_id="prior.role",
            version="0.1.0",
            kind=ProbabilisticPriorKind.NORMAL,
            parameters=(0.0, 1.0),
            evidence=(reference,),
        )
    with pytest.raises(ValidationError):
        PosteriorEstimate(
            feature_id="feature.role",
            kind=PosteriorEstimateKind.SCALAR,
            unit="probability",
            estimate_value=0.5,
            evidence=(reference,),
        )
    with pytest.raises(ValidationError):
        ProbabilisticEstimatorConfiguration(
            configuration_id="configuration.role",
            version="0.1.0",
            estimator_family=ProbabilisticEstimatorFamily.STRUCTURE_AWARE,
            objective="locked objective",
            priors=(
                ProbabilisticPrior(
                    prior_id="prior.valid",
                    version="0.1.0",
                    kind=ProbabilisticPriorKind.NORMAL,
                    parameters=(0.0, 1.0),
                ),
            ),
            optimizer="deterministic",
            seed=1,
            max_iterations=2,
            reference=request.configuration.reference,
            evidence=(reference,),
        )
    with pytest.raises(ValidationError):
        EstimatorConstraint(
            constraint_id="constraint.role",
            expression="x >= 0",
            hard=True,
            evidence=(reference,),
        )
    with pytest.raises(ValidationError):
        OptimizationDiagnostic(
            diagnostic_id="diagnostic.role",
            status=OptimizationDiagnosticStatus.NOT_EVALUABLE,
            objective="locked objective",
            iteration_count=0,
            message="role check",
            evidence=(reference,),
        )


def test_request_and_result_binding_failures_are_closed() -> None:
    request = build_request()
    with pytest.raises(ValidationError):
        request.model_validate(
            request.model_dump(mode="python")
            | {"context": request.context.model_copy(update={"request_id": "request.other"})},
            strict=True,
        )
    with pytest.raises(ValidationError):
        request.model_validate(
            request.model_dump(mode="python")
            | {"source_artifacts": (request.source_artifacts[0], request.source_artifacts[0])},
            strict=True,
        )
    result = M1004Service().execute(request)
    with pytest.raises(ValidationError):
        type(result).model_validate(
            result.model_dump(mode="python") | {"request_digest": "sha256:" + "0" * 64},
            strict=True,
        )
    with pytest.raises(ValidationError):
        type(result).model_validate(
            result.model_dump(mode="python") | {"result_id": "result.wrong"}, strict=True
        )
    with pytest.raises(ValidationError):
        type(result).model_validate(
            result.model_dump(mode="python") | {"evidence": ()}, strict=True
        )
    with pytest.raises(ValidationError):
        type(result).model_validate(
            result.model_dump(mode="python") | {"human_review_required": False}, strict=True
        )


def test_result_closure_exercises_estimated_and_abstained_branches() -> None:
    service = M1004Service()
    result = service.execute(build_request())
    estimate = PosteriorEstimate(
        feature_id="feature.discordance",
        kind=PosteriorEstimateKind.SCALAR,
        unit="probability",
        estimate_value=0.5,
    )
    payload = result.model_dump(mode="python")
    payload.update(
        status=ProbabilisticResultStatus.ESTIMATED,
        estimates=(estimate,),
        abstention_reason=None,
        support_decision=SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="supported.fixture",
            rationale="locked fixture support",
        ),
    )
    payload["result_digest"] = result_payload_digest(type(result).model_construct(**payload))
    estimated = type(result).model_validate(payload, strict=True)
    assert estimated.status is ProbabilisticResultStatus.ESTIMATED
    for update in (
        {"status": ProbabilisticResultStatus.ESTIMATED, "estimates": (), "abstention_reason": None},
        {
            "status": ProbabilisticResultStatus.ESTIMATED,
            "estimates": (estimate,),
            "abstention_reason": "still abstained",
        },
        {
            "status": ProbabilisticResultStatus.ESTIMATED,
            "estimates": (estimate,),
            "abstention_reason": None,
        },
        {"estimates": (estimate,)},
        {"abstention_reason": None},
        {
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED, reason_code="supported", rationale="supported"
            )
        },
    ):
        invalid = result.model_dump(mode="python") | update
        invalid["result_digest"] = result_payload_digest(type(result).model_construct(**invalid))
        with pytest.raises(ValidationError):
            type(result).model_validate(invalid, strict=True)
    invalid_digest = estimated.model_dump(mode="python") | {"result_digest": "sha256:" + "2" * 64}
    with pytest.raises(ValidationError):
        type(result).model_validate(invalid_digest, strict=True)
