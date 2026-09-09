"""Adversarial contract and replay-boundary tests for M08-03."""

from __future__ import annotations

import pytest
from evals.m08_03.fixtures import request, typed_request

from glio_proteogen.contracts.m08_03 import (
    M0803_M0802_RESULT_MEDIA_TYPE,
    BaselineFeatureObservation,
    BaselineFeatureState,
    EstimateProteinSubtypeBaselineRequest,
    GliomaEvidenceState,
)
from glio_proteogen.modules.c08_transcript_protein.m08_03_mature_baseline_estimator import (
    engine as engine_module,
)
from glio_proteogen.modules.c08_transcript_protein.m08_03_mature_baseline_estimator.engine import (
    M0803BaselineEngine,
    _initial_typed_program_value,
    _validate_json_request,
    preflight_baseline_authorization,
    verify_m0803_result,
)
from glio_proteogen.modules.c08_transcript_protein.m08_03_mature_baseline_estimator.plugin import (
    M0803Plugin,
)
from glio_proteogen.modules.c08_transcript_protein.m08_03_mature_baseline_estimator.service import (
    M0803Service,
)


def test_empty_feature_domain_abstains_safely() -> None:
    candidate = request(values=())
    # ``values=()`` creates an empty feature domain and exercises incomplete input.
    result = M0803Service().execute(candidate)
    assert result.status.value == "abstained"
    assert result.findings


def test_duplicate_feature_ids_are_rejected() -> None:
    candidate = request()
    with pytest.raises(ValueError, match="feature ids"):
        EstimateProteinSubtypeBaselineRequest(
            **candidate.model_dump(mode="python")
            | {"features": (candidate.features[0], candidate.features[0])}
        )


def test_observed_feature_requires_numeric_value() -> None:
    with pytest.raises(ValueError, match="requires a value"):
        BaselineFeatureObservation(
            feature_id="feature.missing-value",
            state=BaselineFeatureState.OBSERVED,
            unit="z-score",
        )


def test_representation_handoff_media_type_is_strict() -> None:
    candidate = request()
    with pytest.raises(ValueError, match="M08-02"):
        EstimateProteinSubtypeBaselineRequest(
            **candidate.model_dump(mode="python")
            | {
                "representation_result": candidate.representation_result.model_copy(
                    update={"media_type": "application/json"}
                )
            }
        )
    assert candidate.representation_result.media_type == M0803_M0802_RESULT_MEDIA_TYPE


def test_hostile_control_object_fails_closed() -> None:
    class Hostile:
        @property
        def context(self) -> object:
            raise RuntimeError

    with pytest.raises(PermissionError):
        preflight_baseline_authorization(Hostile())


def test_json_request_byte_limit_is_enforced() -> None:
    candidate = request()
    with pytest.raises(ValueError, match="byte limit"):
        _validate_json_request(
            candidate.model_dump(mode="json"),
            b"x" * (4 * 1024 * 1024 + 1),
        )


def test_engine_type_and_result_tamper_guards() -> None:
    engine = M0803BaselineEngine()
    with pytest.raises(TypeError, match="validated request"):
        engine.estimate_validated(object())  # type: ignore[arg-type]
    result = engine.estimate(request())
    with pytest.raises(ValueError, match="digest"):
        verify_m0803_result(result.model_copy(update={"request_digest": "sha256:" + "0" * 64}))


def test_typed_program_initialization_projects_observed_center_to_censor_bound() -> None:
    observed = next(
        item
        for item in typed_request().program_observations
        if item.program.value == "proliferation"
    )
    censored = observed.model_copy(
        update={
            "state": GliomaEvidenceState.LEFT_CENSORED,
            "standardized_effect": None,
            "censoring_limit": -0.25,
        }
    )

    assert _initial_typed_program_value((observed, censored), None) == pytest.approx(-0.25)


def test_typed_censor_only_program_starts_neutral_for_positive_limit() -> None:
    observed = next(iter(typed_request().program_observations))
    censored = observed.model_copy(
        update={
            "state": GliomaEvidenceState.LEFT_CENSORED,
            "standardized_effect": None,
            "censoring_limit": 0.25,
        }
    )

    assert _initial_typed_program_value((censored,), None) == pytest.approx(0.0)


def test_typed_graph_fit_keeps_an_objective_safe_trace() -> None:
    fit = engine_module._typed_fit_graph(typed_request())

    assert fit.objective_trace
    assert fit.objective == pytest.approx(fit.objective_trace[-1], abs=1e-12)
    assert all(
        later <= earlier + engine_module._TYPED_OBJECTIVE_TOLERANCE
        for earlier, later in zip(fit.objective_trace, fit.objective_trace[1:], strict=False)
    )


def test_typed_graph_fit_is_invariant_to_relation_declaration_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = typed_request()
    baseline = engine_module._typed_fit_graph(request)
    monkeypatch.setattr(engine_module, "_TYPED_EDGES", tuple(reversed(engine_module._TYPED_EDGES)))
    reordered = engine_module._typed_fit_graph(request)

    assert reordered.values == baseline.values
    assert reordered.objective_trace == baseline.objective_trace


def test_plugin_descriptor_and_forged_seal() -> None:
    plugin = M0803Plugin(M0803Service())
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M08-03"
    token = plugin.validate(request())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(type(token)(request=token.request, _seal=object()))
