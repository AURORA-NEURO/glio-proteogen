"""Adversarial contract and replay-boundary tests for M08-03."""

from __future__ import annotations

import pytest
from evals.m08_03.fixtures import request

from glio_proteogen.contracts.m08_03 import (
    M0803_M0802_RESULT_MEDIA_TYPE,
    BaselineFeatureObservation,
    BaselineFeatureState,
    EstimateProteinSubtypeBaselineRequest,
)
from glio_proteogen.modules.c08_transcript_protein.m08_03_mature_baseline_estimator.engine import (
    M0803BaselineEngine,
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


def test_plugin_descriptor_and_forged_seal() -> None:
    plugin = M0803Plugin(M0803Service())
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M08-03"
    token = plugin.validate(request())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(type(token)(request=token.request, _seal=object()))
