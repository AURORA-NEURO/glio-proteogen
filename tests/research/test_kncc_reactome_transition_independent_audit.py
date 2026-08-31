from __future__ import annotations

from copy import deepcopy

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from glio_proteogen.adapters.longitudinal_gbm_reactome_transition import router
from glio_proteogen.research.longitudinal_gbm_reactome_transition.contracts import (
    LongitudinalGbmReactomeTransitionRequest,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.demo import (
    synthetic_demo_request,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.fitted_catalog import (
    _derive_design,
    reactome_conditional_fitted_catalog,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.profile import (
    algorithm_profile,
)


def test_source_bootstrap_design_reconstructs_draw_local_eligibility() -> None:
    catalog = reactome_conditional_fitted_catalog()
    draw_index = next(
        index
        for index in range(catalog.bootstrap_replicate_count)
        if np.any((catalog.bootstrap_effects[index] != 0.0) & ~catalog.reference_eligible)
    )
    draw = catalog.bootstrap_draw(draw_index)
    expected, _ = _derive_design(
        np.asarray(draw.effect, dtype=np.float64),
        np.asarray(draw.effect != 0.0, dtype=np.bool_),
        tuple(pathway.member_local_indices for pathway in catalog.pathways),
        catalog.membership_degree,
    )

    assert np.array_equal(catalog.design_for_bootstrap(draw_index), expected)


def test_profile_fitted_counts_exclude_zero_loading_ineligible_features() -> None:
    catalog = reactome_conditional_fitted_catalog()
    profile = algorithm_profile()

    assert profile.counts.fitted_global_feature_count == int(
        np.count_nonzero(catalog.reference_eligible)
    )
    for summary, pathway in zip(profile.pathways, catalog.pathways, strict=True):
        expected = sum(
            bool(catalog.reference_eligible[position])
            for position in pathway.member_local_indices
        )
        assert summary.fitted_feature_count == expected
        assert summary.fitted_feature_count <= summary.mapped_feature_count


def _six_transition_document(bootstrap_replicates: int) -> dict[str, object]:
    document = synthetic_demo_request().model_dump(mode="python")
    template = document["time_points"][0]
    template["observations"] = template["observations"][:2]
    points: list[dict[str, object]] = []
    for point_index in range(7):
        point = deepcopy(template)
        point["time_point_id"] = f"audit.time.{point_index}"
        point["time_offset_days"] = float(point_index * 30)
        for observation_index, observation in enumerate(point["observations"]):
            observation["observation_id"] = (
                f"audit.observation.{point_index}.{observation_index}"
            )
        points.append(point)
    document["time_points"] = tuple(points)
    document["bootstrap_replicates"] = bootstrap_replicates
    return document


def test_solver_work_gate_accepts_boundary_and_rejects_next_bootstrap() -> None:
    boundary = _six_transition_document(194)
    accepted = LongitudinalGbmReactomeTransitionRequest.model_validate(
        boundary,
        strict=True,
    )

    assert (len(accepted.time_points) - 1) * (
        186 + 3 * accepted.bootstrap_replicates
    ) == 4_608
    with pytest.raises(ValidationError, match="4608 solver-work-unit limit"):
        LongitudinalGbmReactomeTransitionRequest.model_validate(
            _six_transition_document(195),
            strict=True,
        )


def test_http_boundary_sanitizes_solver_work_rejection() -> None:
    app = FastAPI()
    app.include_router(router)

    response = TestClient(app).post(
        "/v1/research/longitudinal-gbm-reactome-transition/analyze",
        json=_six_transition_document(195),
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "request does not satisfy the Reactome transition contract"
    }
    assert response.headers["cache-control"] == "no-store"
