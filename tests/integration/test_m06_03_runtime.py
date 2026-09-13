"""Runtime, replay, and sealing checks for provisional M06-03."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

import pytest
from evals.m06_03.run import build_scenario
from pydantic import TypeAdapter

from glio_proteogen.contracts.m06_03 import (
    BaselineResultStatus,
    EstimateProteinAbundanceBaselineResult,
    GliomaBaselineProgram,
    GliomaFeatureAnnotation,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c06_estimation.m06_03_mature_baseline_estimator import (
    M0603MatureBaselineEngine,
    M0603Plugin,
    M0603Service,
    estimate_protein_abundance_baseline,
)
from glio_proteogen.modules.c06_estimation.m06_03_mature_baseline_estimator import (
    kernel as kernel_module,
)
from glio_proteogen.modules.c06_estimation.m06_03_mature_baseline_estimator.engine import (
    PtmBaselineAuthorizationError,
    _validate_json_request,
)

if TYPE_CHECKING:
    from glio_proteogen.contracts.m06_03 import EstimateProteinAbundanceBaselineRequest

pytestmark = pytest.mark.integration
_EXPECTED_TYPED_PROGRAM_STATES = 2
_FIRST_CANDIDATE_CALL = 2


def _request(case_id: str = "clear") -> EstimateProteinAbundanceBaselineRequest:
    return build_scenario(case_id).request


def test_clear_request_emits_scalar_interval_and_categorical_estimates() -> None:
    result = estimate_protein_abundance_baseline(_request())

    assert result.status is BaselineResultStatus.ESTIMATED
    assert tuple(item.kind.value for item in result.estimates) == (
        "scalar",
        "interval",
        "categorical",
    )
    assert result.abstention_reason is None
    assert result.emits_parent is False


def test_typed_glioma_baseline_fits_program_states_with_bootstrap_intervals() -> None:
    request = _request().model_copy(
        update={
            "configuration": _request().configuration.model_copy(
                update={
                    "glioma_annotations": (
                        GliomaFeatureAnnotation(
                            feature_id="feature.scalar",
                            program=GliomaBaselineProgram.RTK_PI3K_AKT_MTOR,
                            direction=1,
                            standard_error=0.2,
                        ),
                        GliomaFeatureAnnotation(
                            feature_id="feature.interval",
                            program=GliomaBaselineProgram.P53_CELL_CYCLE,
                            direction=-1,
                            standard_error=0.2,
                        ),
                    ),
                    "bootstrap_replicates": 16,
                }
            )
        }
    )
    result = M0603MatureBaselineEngine().estimate(request)
    assert result.status is BaselineResultStatus.ESTIMATED
    assert len(result.program_states) == _EXPECTED_TYPED_PROGRAM_STATES
    assert {state.program for state in result.program_states} == {
        GliomaBaselineProgram.RTK_PI3K_AKT_MTOR,
        GliomaBaselineProgram.P53_CELL_CYCLE,
    }
    assert all(
        state.lower_bound <= state.score <= state.upper_bound
        and state.evidence_count >= 1
        and state.top_drivers
        and state.ablation_effects
        for state in result.program_states
    )
    assert any(item.metric_name == "program_score" for item in result.diagnostics)
    assert M0603MatureBaselineEngine().estimate(request) == result


def test_typed_solver_backtracks_objective_increase(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    request = _request().model_copy(
        update={
            "configuration": _request().configuration.model_copy(
                update={
                    "glioma_annotations": (
                        GliomaFeatureAnnotation(
                            feature_id="feature.scalar",
                            program=GliomaBaselineProgram.RTK_PI3K_AKT_MTOR,
                            direction=1,
                            standard_error=0.2,
                        ),
                        GliomaFeatureAnnotation(
                            feature_id="feature.interval",
                            program=GliomaBaselineProgram.P53_CELL_CYCLE,
                            direction=-1,
                            standard_error=0.2,
                        ),
                    )
                }
            )
        }
    )
    observations, reason = kernel_module._observations(request)
    assert reason is None
    center, scale = kernel_module._robust_location_scale(
        observation.value for observation in observations
    )
    baseline = kernel_module._fit(observations, center, scale)
    assert baseline.converged
    original = kernel_module._objective
    calls = 0

    def objective(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        value = original(*args, **kwargs)
        return value + 100.0 if calls == _FIRST_CANDIDATE_CALL else value

    monkeypatch.setattr(kernel_module, "_objective", objective)
    fit = kernel_module._fit(observations, center, scale)
    assert fit.converged
    assert calls > _FIRST_CANDIDATE_CALL
    assert fit.objective <= baseline.objective + kernel_module._OBJECTIVE_TOLERANCE


def test_typed_glioma_baseline_excludes_non_numeric_values_and_abstains_if_empty() -> None:
    request = _request().model_copy(
        update={
            "configuration": _request().configuration.model_copy(
                update={
                    "glioma_annotations": (
                        GliomaFeatureAnnotation(
                            feature_id="feature.category",
                            program=GliomaBaselineProgram.MESENCHYMAL_PROGRAM,
                        ),
                    )
                }
            )
        }
    )
    result = M0603MatureBaselineEngine().estimate(request)
    assert result.status is BaselineResultStatus.ABSTAINED
    assert result.program_states == ()
    assert result.abstention_reason == (
        "typed glioma baseline requires observed scalar or interval evidence"
    )


def test_missing_formal_state_abstains_without_partial_estimates() -> None:
    result = M0603MatureBaselineEngine().estimate(_request("missing"))

    assert result.status is BaselineResultStatus.ABSTAINED
    assert result.estimates == ()
    assert result.abstention_reason == "formal-state feature is missing or unsupported"


def test_upstream_non_valid_result_abstains_before_kernel() -> None:
    result = M0603MatureBaselineEngine().estimate(_request("upstream-abstained"))

    assert result.status is BaselineResultStatus.ABSTAINED
    assert result.estimates == ()
    assert result.diagnostics[0].status.value == "not_evaluable"


def test_service_and_engine_are_exactly_equal() -> None:
    request = _request()
    assert M0603Service()._execute_validated(request) == M0603MatureBaselineEngine().estimate(
        request
    )


def test_plugin_typed_and_canonical_json_validation_are_equal() -> None:
    request = _request()
    plugin = M0603Plugin(M0603Service())
    payload = canonical_json_bytes(request.model_dump(mode="json"))

    typed_result = plugin.run(plugin.validate(request))
    json_result = plugin.run(plugin.validate(payload))

    assert typed_result == json_result
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M06-03"


def test_plugin_rejects_forged_execution_token() -> None:
    plugin = M0603Plugin(M0603Service())
    token = plugin.validate(_request())

    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]

    assert plugin.run(token).status is BaselineResultStatus.ESTIMATED


def test_plugin_rejects_mutated_token_request() -> None:
    plugin = M0603Plugin(M0603Service())
    token = plugin.validate(_request())
    object.__setattr__(token, "request", _request("missing"))

    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(token)


def test_stale_upstream_digest_is_rejected() -> None:
    request = _request()
    stale_upstream = request.formal_state_result.model_copy(
        update={"request_digest": "sha256:" + "0" * 64}
    )
    stale_request = request.model_copy(update={"formal_state_result": stale_upstream})

    with pytest.raises(ValueError, match="stale"):
        M0603MatureBaselineEngine().estimate_validated(stale_request)


def test_schema_replay_mismatch_is_rejected() -> None:
    request = _request()
    altered_schema = request.state_schema.model_copy(update={"schema_id": "schema.other"})

    with pytest.raises(ValueError, match="schema replay"):
        M0603MatureBaselineEngine().estimate_validated(
            request.model_copy(update={"state_schema": altered_schema})
        )


@pytest.mark.parametrize(
    "role",
    [
        "approved_configuration",
        "identity_lineage",
        "provenance",
        "consent",
        "quality",
        "support",
        "intended_use",
    ],
)
def test_each_control_denies_before_execution(role: str) -> None:
    request = _request()
    denied_context = copy.deepcopy(request.context)
    state = "unresolved" if role == "identity_lineage" else "rejected"
    if role == "consent":
        state = "denied"
    object.__setattr__(getattr(denied_context.references, role), "state", state)
    denied_request = request.model_copy(update={"context": denied_context})

    with pytest.raises(PtmBaselineAuthorizationError):
        M0603Service().validate_request(denied_request)


def test_invalid_authorization_candidates_fail_closed() -> None:
    with pytest.raises(PtmBaselineAuthorizationError):
        M0603Service().validate_request(object())

    class ExplodingMapping(dict[str, object]):
        def get(self, key: str, _default: object = None) -> object:
            raise RuntimeError(key)

    with pytest.raises(PtmBaselineAuthorizationError):
        M0603Service().validate_request(ExplodingMapping())


def test_json_request_byte_cap_precedes_validation() -> None:
    with pytest.raises(ValueError, match="byte limit"):
        _validate_json_request({}, b"x" * (4 * 1024 * 1024 + 1))


def test_engine_rejects_wrong_validated_type_and_feature_replay() -> None:
    engine = M0603MatureBaselineEngine()
    with pytest.raises(TypeError, match="declared request type"):
        engine.estimate_validated(object())  # type: ignore[arg-type]

    request = _request()
    changed_values = tuple(reversed(request.feature_values))
    with pytest.raises(ValueError, match="feature replay"):
        engine.estimate_validated(request.model_copy(update={"feature_values": changed_values}))


def test_service_execute_runs_validate_then_execute() -> None:
    result = M0603Service().execute(_request())
    assert result.status is BaselineResultStatus.ESTIMATED


def test_request_validator_rejects_all_replay_bindings() -> None:
    request = _request()
    adapter = TypeAdapter(type(request))

    altered_schema = request.state_schema.model_copy(update={"schema_id": "schema.other"})
    with pytest.raises(ValueError, match="state schema"):
        adapter.validate_python(
            request.model_copy(update={"state_schema": altered_schema}), strict=True
        )

    altered_values = tuple(reversed(request.feature_values))
    with pytest.raises(ValueError, match="feature values"):
        adapter.validate_python(
            request.model_copy(update={"feature_values": altered_values}), strict=True
        )

    duplicate = request.feature_values[0].model_copy(
        update={"feature_id": request.feature_values[1].feature_id}
    )
    duplicate_values = (duplicate, *request.feature_values[1:])
    duplicate_upstream_request = request.formal_state_result.request.model_copy(
        update={"values": duplicate_values}
    )
    duplicate_upstream_result = request.formal_state_result.model_copy(
        update={"request": duplicate_upstream_request}
    )
    with pytest.raises(ValueError, match="unique"):
        adapter.validate_python(
            request.model_copy(
                update={
                    "formal_state_result": duplicate_upstream_result,
                    "feature_values": duplicate_values,
                }
            ),
            strict=True,
        )

    subset = request.feature_values[:2]
    upstream_fields = dict(request.formal_state_result.request.__dict__)
    upstream_fields["values"] = subset
    upstream_request = request.formal_state_result.request.model_construct(
        **upstream_fields,
    )
    upstream_result = request.formal_state_result.model_copy(update={"request": upstream_request})
    malformed_fields = dict(request.__dict__)
    malformed_fields["formal_state_result"] = upstream_result
    malformed_fields["feature_values"] = subset
    malformed_subset = request.model_construct(**malformed_fields)
    with pytest.raises(ValueError, match="cover"):
        malformed_subset.request_is_bound()  # type: ignore[operator]

    configuration = request.configuration.model_copy(update={"state_schema_id": "schema.other"})
    with pytest.raises(ValueError, match="configuration"):
        adapter.validate_python(
            request.model_copy(update={"configuration": configuration}), strict=True
        )


def test_result_validator_rejects_digest_status_and_support_tampering() -> None:
    request = _request()
    result = M0603MatureBaselineEngine().estimate(request)
    adapter = TypeAdapter(EstimateProteinAbundanceBaselineResult)

    with pytest.raises(ValueError, match="request digest"):
        adapter.validate_python(
            result.model_copy(update={"request_digest": "sha256:" + "0" * 64}), strict=True
        )
    with pytest.raises(ValueError, match="estimated result"):
        adapter.validate_python(result.model_copy(update={"estimates": ()}), strict=True)
    with pytest.raises(ValueError, match="supported status"):
        adapter.validate_python(
            result.model_copy(
                update={
                    "support_decision": result.support_decision.model_copy(
                        update={"status": SupportStatus.UNSUPPORTED}
                    )
                }
            ),
            strict=True,
        )
    with pytest.raises(ValueError, match="abstained result"):
        adapter.validate_python(
            result.model_copy(update={"status": BaselineResultStatus.ABSTAINED}), strict=True
        )
    with pytest.raises(ValueError, match="result digest"):
        adapter.validate_python(
            result.model_copy(update={"result_digest": "sha256:" + "0" * 64}), strict=True
        )
