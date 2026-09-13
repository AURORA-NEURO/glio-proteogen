"""Adversarial runtime and adapter coverage for M10-05."""

# Constraint values are intentionally literal fixtures.
# ruff: noqa: PLR2004

from __future__ import annotations

import json
from itertools import pairwise
from typing import TYPE_CHECKING

import pytest
from evals.m10_05.run import build_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import glio_proteogen.modules.c10_pathway_proteotype_factors.m10_05_mechanism_constraint_integrator.engine as engine_module  # noqa: E501
from glio_proteogen.adapters.m1005 import create_m1005_app, m1005_app
from glio_proteogen.contracts.m10_05 import (
    ConstraintAblation,
    ConstraintAwareEstimate,
    ConstraintEvaluationOutcome,
    ConstraintHardness,
    ConstraintKind,
    FeatureObservation,
    FeatureObservationState,
    GliomaConstraintProgram,
    MechanismConstraint,
    MechanismConstraintSet,
    ProteinRnaConstraintIntegrationResult,
    canonical_request_digest,
    normalized_request,
)
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.modules.c10_pathway_proteotype_factors.m10_05_mechanism_constraint_integrator import (  # noqa: E501
    M1005ConstraintAuthorizationError,
    M1005Plugin,
    M1005ReplayVerificationError,
    M1005Service,
    integrate_protein_rna_constraints,
)

if TYPE_CHECKING:
    from pathlib import Path

HTTP_OK = 200
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_BAD_REQUEST = 400
HTTP_UNPROCESSABLE = 422
HTTP_CONFLICT = 409
CLI_AUTH_ERROR = 2
CLI_FAILURE = 1


def test_integrator_reports_soft_conflict_and_ablation() -> None:
    result = M1005Service().execute(build_request(soft_expression="always_false"))
    assert result.status.value == "integrated"
    assert result.evaluations[1].outcome is ConstraintEvaluationOutcome.VIOLATED
    assert result.ablations[0].effect_delta == 0.0
    assert result.human_review_required is True
    assert result.emits_parent is False


def test_numeric_feature_constraint_uses_measured_value_and_error() -> None:
    request = build_request(
        hard_expression="feature.pathway >= 0.5",
        soft_expression="feature.pathway <= 1.0",
    ).model_copy(
        update={
            "feature_observations": (
                FeatureObservation(
                    feature_id="feature.pathway",
                    state=FeatureObservationState.OBSERVED,
                    value=0.8,
                    standard_error=0.1,
                ),
            )
        }
    )
    result = M1005Service().execute(request)
    assert result.status.value == "integrated"
    assert all(item.outcome is ConstraintEvaluationOutcome.SATISFIED for item in result.evaluations)
    assert result.estimates[0].score == 1.0
    assert result.ablations[0].effect_delta == 0.4


def test_typed_glioma_constraint_graph_emits_replayable_program_states() -> None:
    request = build_request(
        hard_expression="feature.pathway >= 0.5",
        soft_expression="feature.pathway <= 1.0",
        measured=True,
    )
    artifacts = (
        request.feature_artifacts[0],
        *tuple(
            request.feature_artifacts[0].model_copy(
                update={
                    "artifact_id": f"feature.{name}",
                    "digest": f"sha256:{fill * 64}",
                }
            )
            for name, fill in (("rtk", "c"), ("p53", "d"), ("idh", "e"))
        ),
    )
    typed_request = request.model_copy(
        update={
            "feature_artifacts": artifacts,
            "feature_observations": (
                FeatureObservation(
                    feature_id="feature.pathway",
                    state=FeatureObservationState.OBSERVED,
                    value=0.8,
                    standard_error=0.1,
                    program=GliomaConstraintProgram.RTK_PI3K_AKT_MTOR,
                ),
                FeatureObservation(
                    feature_id="feature.rtk",
                    state=FeatureObservationState.OBSERVED,
                    value=1.2,
                    standard_error=0.1,
                    quality_weight=0.9,
                    program=GliomaConstraintProgram.RTK_PI3K_AKT_MTOR,
                ),
                FeatureObservation(
                    feature_id="feature.p53",
                    state=FeatureObservationState.OBSERVED,
                    value=-0.8,
                    standard_error=0.2,
                    quality_weight=0.8,
                    program=GliomaConstraintProgram.P53_CELL_CYCLE,
                ),
                FeatureObservation(
                    feature_id="feature.idh",
                    state=FeatureObservationState.OBSERVED,
                    value=0.4,
                    standard_error=0.15,
                    quality_weight=1.0,
                    program=GliomaConstraintProgram.IDH_HIF1A,
                ),
            ),
            "bootstrap_replicates": 16,
        }
    )
    service = M1005Service()
    result = service.execute(typed_request)
    assert result.status.value == "integrated"
    assert result.typed_model is True
    assert result.solver_iterations is not None
    assert result.solver_objective is not None
    assert {state.program for state in result.program_states} == {
        GliomaConstraintProgram.RTK_PI3K_AKT_MTOR,
        GliomaConstraintProgram.P53_CELL_CYCLE,
        GliomaConstraintProgram.IDH_HIF1A,
    }
    assert all(
        state.lower_bound <= state.score <= state.upper_bound for state in result.program_states
    )
    assert all(
        state.evidence_count >= 1 and state.ablation_effects for state in result.program_states
    )
    assert service.verify(result).result_digest == result.result_digest


def test_typed_program_initialization_downweights_failed_replicate() -> None:
    terms = (
        (0.2, 0.2, 1.0),
        (0.3, 0.2, 1.0),
        (4.0, 0.2, 1.0),
    )

    center = engine_module._robust_initial_program_center(terms)
    arithmetic_mean = sum(term[0] for term in terms) / len(terms)

    assert center < 0.5
    assert arithmetic_mean > 1.0
    assert engine_module._initial_program_measurement_objective(center, terms) <= (
        engine_module._initial_program_measurement_objective(arithmetic_mean, terms)
    )


def test_typed_program_solver_backtracks_objective_increase(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    observations = (
        engine_module._TypedObservation(
            feature_id="protein.egfr",
            program=GliomaConstraintProgram.RTK_PI3K_AKT_MTOR,
            direction=1,
            state=FeatureObservationState.OBSERVED,
            value=1.2,
            standard_error=0.2,
            quality_weight=1.0,
            evidence=(),
        ),
        engine_module._TypedObservation(
            feature_id="protein.tp53",
            program=GliomaConstraintProgram.P53_CELL_CYCLE,
            direction=-1,
            state=FeatureObservationState.OBSERVED,
            value=-0.8,
            standard_error=0.2,
            quality_weight=0.9,
            evidence=(),
        ),
        engine_module._TypedObservation(
            feature_id="protein.idh1",
            program=GliomaConstraintProgram.IDH_HIF1A,
            direction=1,
            state=FeatureObservationState.OBSERVED,
            value=0.4,
            standard_error=0.15,
            quality_weight=1.0,
            evidence=(),
        ),
        engine_module._TypedObservation(
            feature_id="protein.mki67",
            program=GliomaConstraintProgram.PROLIFERATION,
            direction=1,
            state=FeatureObservationState.OBSERVED,
            value=0.6,
            standard_error=0.25,
            quality_weight=0.8,
            evidence=(),
        ),
    )
    original = engine_module._program_objective
    calls = 0

    def objective(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        value = original(*args, **kwargs)
        return value + 100.0 if calls == 2 else value

    monkeypatch.setattr(engine_module, "_program_objective", objective)
    fit = engine_module._fit_programs(observations, 0.0, 1.0)
    assert fit.converged
    assert calls > 2
    assert all(
        after <= before + engine_module._PROGRAM_OBJECTIVE_TOLERANCE
        for before, after in pairwise(fit.objective_trace)
    )


def test_typed_normalization_ignores_left_censor_limits() -> None:
    observations = (
        engine_module._TypedObservation(
            feature_id="feature.observed",
            program=GliomaConstraintProgram.RTK_PI3K_AKT_MTOR,
            direction=1,
            state=FeatureObservationState.OBSERVED,
            value=1.0,
            standard_error=0.1,
            quality_weight=1.0,
            evidence=(),
        ),
        engine_module._TypedObservation(
            feature_id="feature.censored",
            program=GliomaConstraintProgram.P53_CELL_CYCLE,
            direction=1,
            state=FeatureObservationState.LEFT_CENSORED,
            value=50.0,
            standard_error=0.1,
            quality_weight=1.0,
            evidence=(),
        ),
    )
    assert engine_module._typed_location_scale(observations) == (1.0, 1.0)


def test_typed_inhibitory_censor_reverses_program_bound() -> None:
    inhibitory = engine_module._TypedObservation(
        feature_id="feature.pten",
        program=GliomaConstraintProgram.RTK_PI3K_AKT_MTOR,
        direction=-1,
        state=FeatureObservationState.LEFT_CENSORED,
        value=-0.5,
        standard_error=0.1,
        quality_weight=1.0,
        evidence=(),
    )
    target = engine_module._typed_target(inhibitory, 0.0, 1.0)
    assert target == pytest.approx(0.5)
    assert engine_module._typed_residual(inhibitory, 0.0, target) == pytest.approx(0.5)
    assert engine_module._typed_gradient_residual(inhibitory, 0.0, target) == pytest.approx(-0.5)
    assert engine_module._typed_residual(inhibitory, 1.0, target) == pytest.approx(0.0)


def test_typed_missing_evidence_abstains_without_negative_state() -> None:
    request = build_request().model_copy(
        update={
            "feature_observations": (
                FeatureObservation(
                    feature_id="feature.pathway",
                    state=FeatureObservationState.MISSING,
                    quality_weight=0.0,
                    program=GliomaConstraintProgram.RTK_PI3K_AKT_MTOR,
                ),
            ),
            "bootstrap_replicates": 16,
        }
    )
    result = M1005Service().execute(request)
    assert result.status.value == "abstained"
    assert result.program_states == ()
    assert result.support_decision.status.value == "review_required"
    assert "typed glioma constraint graph" in (result.abstention_reason or "")


def test_numeric_soft_violation_is_weighted_and_visible_in_ablation() -> None:
    request = build_request(
        hard_expression="feature.pathway >= 0.5",
        soft_expression="feature.pathway <= 1.0",
    ).model_copy(
        update={
            "feature_observations": (
                FeatureObservation(
                    feature_id="feature.pathway",
                    state=FeatureObservationState.OBSERVED,
                    value=1.2,
                    standard_error=0.2,
                ),
            )
        }
    )
    result = M1005Service().execute(request)
    assert result.status.value == "integrated"
    assert result.evaluations[1].outcome is ConstraintEvaluationOutcome.VIOLATED
    assert 0.0 < result.ablations[0].effect_delta < 0.4
    assert result.human_review_required is True


def test_numeric_hard_violation_abstains_and_missing_is_not_negative() -> None:
    violated = build_request(hard_expression="feature.pathway >= 0.5").model_copy(
        update={
            "feature_observations": (
                FeatureObservation(
                    feature_id="feature.pathway",
                    state=FeatureObservationState.OBSERVED,
                    value=0.1,
                    standard_error=0.1,
                ),
            )
        }
    )
    result = M1005Service().execute(violated)
    assert result.status.value == "abstained"
    missing = build_request(hard_expression="feature.pathway >= 0.5").model_copy(
        update={
            "feature_observations": (
                FeatureObservation(
                    feature_id="feature.pathway",
                    state=FeatureObservationState.MISSING,
                ),
            )
        }
    )
    missing_result = M1005Service().execute(missing)
    assert missing_result.status.value == "abstained"
    assert missing_result.evaluations[0].outcome is ConstraintEvaluationOutcome.NOT_EVALUABLE


def test_left_censored_upper_bound_can_satisfy_numeric_constraint() -> None:
    request = build_request(
        hard_expression="feature.pathway <= 0.5",
        soft_expression="always_true",
    ).model_copy(
        update={
            "feature_observations": (
                FeatureObservation(
                    feature_id="feature.pathway",
                    state=FeatureObservationState.LEFT_CENSORED,
                    censoring_limit=0.4,
                ),
            )
        }
    )
    result = M1005Service().execute(request)
    assert result.status.value == "integrated"
    assert result.evaluations[0].outcome is ConstraintEvaluationOutcome.SATISFIED


def test_strict_numeric_constraints_respect_equality_and_censoring_boundaries() -> None:
    observed = build_request(hard_expression="feature.pathway > 0.8", measured=True)
    observed_result = M1005Service().execute(observed)

    assert observed_result.status.value == "abstained"
    assert observed_result.evaluations[0].outcome is ConstraintEvaluationOutcome.VIOLATED

    censored = build_request(hard_expression="feature.pathway < 0.8", measured=True).model_copy(
        update={
            "feature_observations": (
                observed.feature_observations[0].model_copy(
                    update={
                        "state": FeatureObservationState.LEFT_CENSORED,
                        "value": None,
                        "censoring_limit": 0.8,
                    }
                ),
            )
        }
    )
    censored_result = M1005Service().execute(censored)

    assert censored_result.status.value == "abstained"
    assert censored_result.evaluations[0].outcome is ConstraintEvaluationOutcome.NOT_EVALUABLE


@pytest.mark.parametrize("expression", ["always_false", "x < 0"])
def test_hard_constraint_violation_abstains(expression: str) -> None:
    result = M1005Service().execute(build_request(hard_expression=expression))
    assert result.status.value == "abstained"
    assert result.estimates == ()
    assert result.support_decision.status.value == "review_required"
    assert result.human_review_required is True


def test_unknown_constraint_language_abstains_without_heuristics() -> None:
    result = M1005Service().execute(build_request(hard_expression="pathway_score > threshold"))
    assert result.status.value == "abstained"
    assert {item.outcome for item in result.evaluations} == {
        ConstraintEvaluationOutcome.NOT_EVALUABLE,
        ConstraintEvaluationOutcome.SATISFIED,
    }
    assert result.support_decision.status.value == "unsupported"


@pytest.mark.parametrize("field", ["approved_configuration", "identity_lineage", "consent"])
def test_control_preflight_fails_before_constraint_traversal(field: str) -> None:
    request = build_request()
    refs = request.context.references
    changed = getattr(refs, field).model_copy(update={"state": "unknown"})
    blocked_refs = refs.model_copy(update={field: changed})
    blocked = request.model_copy(
        update={"context": request.context.model_copy(update={"references": blocked_refs})}
    )
    with pytest.raises(M1005ConstraintAuthorizationError):
        M1005Service().execute(blocked)


def test_plugin_accepts_json_once_and_rejects_copied_token() -> None:
    plugin = M1005Plugin(M1005Service())
    token = plugin.validate(build_request().model_dump_json())
    result = plugin.run(token)
    assert result.request_digest == canonical_request_digest(build_request())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(token.__class__(request=token.request, _seal=object()))


def test_plugin_rejects_mutated_issued_request() -> None:
    plugin = M1005Plugin(M1005Service())
    token = plugin.validate(build_request())
    object.__setattr__(token.request, "request_id", "request.mutated")
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(token)


def test_replay_rejects_every_derived_region_mutation() -> None:
    service = M1005Service()
    result = service.execute(build_request())
    for update in (
        {"result_id": "result.forged"},
        {"evaluations": ()},
        {"limitations": ()},
        {"human_review_required": not result.human_review_required},
    ):
        with pytest.raises((M1005ReplayVerificationError, ValueError)):
            service.verify(result.model_copy(update=update))


def test_verify_without_replay_still_validates_digest() -> None:
    service = M1005Service()
    result = service.execute(build_request())
    assert service.verify(result, replay=False).model_dump() == result.model_dump()
    with pytest.raises((M1005ReplayVerificationError, ValueError)):
        service.verify(result.model_copy(update={"abstention_reason": "tampered"}), replay=False)


def test_duplicate_json_keys_are_rejected_before_validation() -> None:
    with pytest.raises(StrictJsonError):
        strict_json_loads('{"request_id":"a","request_id":"b"}')


def test_api_schema_validate_integrate_and_verify_parity() -> None:
    client = TestClient(create_m1005_app())
    request = build_request()
    payload = request.model_dump_json()
    schema = client.get("/v1/m10-05/schema/request")
    assert schema.status_code == HTTP_OK
    assert schema.json()["x-glio-contract"]["provisionalAbi"] is True
    validated = client.post("/v1/m10-05/validate", content=payload)
    assert validated.status_code == HTTP_OK
    assert validated.json()["valid"] is True
    executed = client.post("/v1/m10-05/integrate", content=payload)
    assert executed.status_code == HTTP_OK
    verified = client.post("/v1/m10-05/verify", content=executed.content)
    assert verified.status_code == HTTP_OK
    assert verified.json()["verified"] is True


def test_api_denies_unaccepted_controls() -> None:
    client = TestClient(create_m1005_app())
    request = build_request(unknown_controls=True)
    response = client.post("/v1/m10-05/integrate", content=request.model_dump_json())
    assert response.status_code == HTTP_FORBIDDEN
    assert "controls" in response.json()["detail"]


def test_cli_validate_integrate_and_export_schema(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_text(build_request().model_dump_json(), encoding="utf-8")
    runner = CliRunner()
    validated = runner.invoke(m1005_app, ["validate", str(request_path)])
    assert validated.exit_code == 0
    integrated = runner.invoke(m1005_app, ["integrate", str(request_path)])
    assert integrated.exit_code == 0
    output_path.write_text(integrated.stdout, encoding="utf-8")
    verified = runner.invoke(m1005_app, ["verify", str(output_path)])
    assert verified.exit_code == 0
    schema = runner.invoke(m1005_app, ["export-schema", "output"])
    assert schema.exit_code == 0
    assert json.loads(schema.stdout)["$id"].endswith(":output")


def test_constraint_contract_rejects_duplicate_features_and_bad_soft_weight() -> None:
    with pytest.raises(ValueError, match="feature ids must be unique"):
        MechanismConstraint(
            constraint_id="constraint.duplicate",
            kind=ConstraintKind.GRAPH,
            hardness=ConstraintHardness.SOFT,
            expression="always_true",
            feature_ids=("feature.x", "feature.x"),
            weight=0.5,
        )
    with pytest.raises(ValueError, match="soft constraints require"):
        MechanismConstraint(
            constraint_id="constraint.no-weight",
            kind=ConstraintKind.GRAPH,
            hardness=ConstraintHardness.SOFT,
            expression="always_true",
            feature_ids=("feature.x",),
        )


def test_service_result_is_deterministic() -> None:
    service = M1005Service()
    first = service.execute(build_request(soft_expression="always_false"))
    second = service.execute(build_request(soft_expression="always_false"))
    assert first.model_dump_json() == second.model_dump_json()
    assert first.result_digest == second.result_digest


def test_contract_relational_negative_matrix() -> None:
    constraint = MechanismConstraint(
        constraint_id="constraint.same",
        kind=ConstraintKind.GRAPH,
        hardness=ConstraintHardness.HARD,
        expression="always_true",
        feature_ids=("feature.x",),
    )
    with pytest.raises(ValueError, match="constraint ids must be unique"):
        MechanismConstraintSet(
            set_id="set.duplicate",
            version="0.1.0",
            reviewed_by="reviewer",
            constraints=(constraint, constraint),
        )
    with pytest.raises(ValueError, match="effect delta"):
        ConstraintAblation(
            constraint_id="constraint.soft",
            with_constraint_effect=0.8,
            without_constraint_effect=0.5,
            effect_delta=0.1,
        )
    with pytest.raises(ValueError, match="bounds are not ordered"):
        ConstraintAwareEstimate(
            estimate_label="bad",
            score=0.5,
            lower_bound=0.8,
            upper_bound=0.2,
        )
    with pytest.raises(ValueError, match="score must lie"):
        ConstraintAwareEstimate(
            estimate_label="bad",
            score=0.9,
            lower_bound=0.1,
            upper_bound=0.5,
        )
    assert ConstraintAwareEstimate(estimate_label="one-sided", score=0.5, lower_bound=0.1)


@pytest.mark.parametrize(
    "mutation",
    [
        {"request_digest": "sha256:" + "0" * 64},
        {"result_id": "result.forged"},
        {"evidence": ()},
        {"ablations": ()},
    ],
)
def test_result_validator_rejects_replay_closure_mutations(
    mutation: dict[str, object],
) -> None:
    result = M1005Service().execute(build_request())
    payload = result.model_dump(mode="python")
    payload.update(mutation)
    with pytest.raises(ValueError, match=r".+"):
        ProteinRnaConstraintIntegrationResult.model_validate(payload, strict=True)


def test_request_validator_rejects_duplicate_artifact_and_wrong_estimator_media() -> None:
    request = build_request()
    with pytest.raises(ValueError, match="estimator result"):
        request.model_validate(
            request.model_dump(mode="python")
            | {
                "advanced_estimator_result": request.representation_result,
            },
            strict=True,
        )
    duplicate = request.model_dump(mode="python")
    duplicate["feature_artifacts"] = (request.representation_result,)
    with pytest.raises(ValueError, match="unique"):
        request.model_validate(duplicate, strict=True)


def test_canonical_dict_projection_and_public_function() -> None:
    request = build_request()
    assert normalized_request(request)["request_id"] == request.request_id
    result = M1005Service().execute(request)
    assert integrate_protein_rna_constraints(request).result_digest == result.result_digest


def test_preflight_hostile_object_and_verify_malformed_result() -> None:
    class Hostile:
        @property
        def context(self) -> object:
            raise RuntimeError

    with pytest.raises(M1005ConstraintAuthorizationError):
        M1005Service().execute(Hostile())
    with pytest.raises(M1005ReplayVerificationError):
        M1005Service().verify({"not": "a result"})


def test_api_and_cli_negative_boundaries(tmp_path: Path) -> None:
    client = TestClient(create_m1005_app())
    unknown_schema = client.get("/v1/m10-05/schema/unknown")
    assert unknown_schema.status_code == HTTP_NOT_FOUND
    invalid_json = client.post("/v1/m10-05/validate", content=b'{"x": 1, "x": 2}')
    assert invalid_json.status_code == HTTP_BAD_REQUEST
    invalid_model = client.post("/v1/m10-05/validate", content=b"{}")
    assert invalid_model.status_code == HTTP_UNPROCESSABLE
    result = M1005Service().execute(build_request()).model_copy(update={"result_id": "forged"})
    tampered = client.post("/v1/m10-05/verify", content=result.model_dump_json())
    assert tampered.status_code == HTTP_CONFLICT
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    runner = CliRunner()
    assert runner.invoke(m1005_app, ["validate", str(bad)]).exit_code == CLI_AUTH_ERROR
    denied = tmp_path / "denied.json"
    denied.write_text(build_request(unknown_controls=True).model_dump_json(), encoding="utf-8")
    assert runner.invoke(m1005_app, ["integrate", str(denied)]).exit_code == CLI_AUTH_ERROR
    assert runner.invoke(m1005_app, ["verify", str(bad)]).exit_code == CLI_FAILURE
