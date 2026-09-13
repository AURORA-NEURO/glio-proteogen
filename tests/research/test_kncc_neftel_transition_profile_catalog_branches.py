from __future__ import annotations

import re
from dataclasses import replace
from typing import TYPE_CHECKING

import numpy as np
import pytest

from glio_proteogen.research.longitudinal_gbm.catalog import longitudinal_gbm_catalog
from glio_proteogen.research.longitudinal_gbm_neftel_transition import catalog as source_module
from glio_proteogen.research.longitudinal_gbm_neftel_transition import demo as demo_module
from glio_proteogen.research.longitudinal_gbm_neftel_transition import profile as profile_module
from glio_proteogen.research.longitudinal_gbm_neftel_transition import service as service_module
from glio_proteogen.research.longitudinal_gbm_neftel_transition.demo import (
    synthetic_demo_request,
)
from glio_proteogen.research.longitudinal_gbm_neftel_transition.errors import (
    NeftelConditionalModelIntegrityError,
    NeftelTransitionSourceIntegrityError,
)
from glio_proteogen.research.longitudinal_gbm_neftel_transition.fitted_catalog import (
    neftel_program_fitted_catalog,
)
from glio_proteogen.research.longitudinal_gbm_neftel_transition.profile import (
    EXPECTED_NUMPY_VERSION,
    algorithm_profile,
)
from glio_proteogen.research.longitudinal_gbm_neftel_transition.service import (
    LongitudinalGbmNeftelTransitionService,
)
from glio_proteogen.research.neftel_protein_programs.catalog import marker_catalog

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _clear_catalog_caches() -> Iterator[None]:
    source_module.neftel_transition_source_catalog.cache_clear()
    neftel_program_fitted_catalog.cache_clear()
    yield
    source_module.neftel_transition_source_catalog.cache_clear()
    neftel_program_fitted_catalog.cache_clear()


def test_source_catalog_rejects_parent_binding_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kncc = longitudinal_gbm_catalog()
    drifted = replace(kncc, content_digest="sha256:" + "0" * 64)
    monkeypatch.setattr(source_module, "longitudinal_gbm_catalog", lambda: drifted)
    with pytest.raises(NeftelTransitionSourceIntegrityError, match="parent catalog binding"):
        source_module.neftel_transition_source_catalog()


def test_source_catalog_rejects_mapping_count_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = dict(source_module.EXPECTED_PROGRAM_MAPPED_COUNTS)
    expected["MES2"] = (50, 50, 42, 39)
    monkeypatch.setattr(source_module, "EXPECTED_PROGRAM_MAPPED_COUNTS", expected)
    with pytest.raises(NeftelTransitionSourceIntegrityError, match="mapping-count"):
        source_module.neftel_transition_source_catalog()


def test_source_catalog_rejects_duplicate_mapped_features(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kncc = longitudinal_gbm_catalog()
    neftel = marker_catalog()
    gene_index = {feature.gene_symbol: index for index, feature in enumerate(kncc.features)}
    programs = dict(neftel.programs)
    mes2 = list(programs["MES2"])
    eligible_positions = [
        position
        for position, marker in enumerate(mes2)
        if marker.normalized_symbol in gene_index
        and kncc.features[gene_index[marker.normalized_symbol]].eligible
    ]
    assert len(eligible_positions) >= 2
    mes2[eligible_positions[1]] = mes2[eligible_positions[0]]
    programs["MES2"] = tuple(mes2)
    drifted = replace(neftel, programs=programs)
    monkeypatch.setattr(source_module, "marker_catalog", lambda: drifted)
    with pytest.raises(NeftelTransitionSourceIntegrityError, match="duplicate features"):
        source_module.neftel_transition_source_catalog()


def test_source_catalog_rejects_union_inventory_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(source_module, "EXPECTED_ELIGIBLE_UNION_FEATURE_COUNT", 257)
    with pytest.raises(NeftelTransitionSourceIntegrityError, match="union-feature inventory"):
        source_module.neftel_transition_source_catalog()


def test_profile_scalar_parsers_fail_closed() -> None:
    with pytest.raises(NeftelConditionalModelIntegrityError, match="not an object"):
        profile_module._mapping([], "field")
    with pytest.raises(NeftelConditionalModelIntegrityError, match="not an array"):
        profile_module._sequence({}, "field")
    with pytest.raises(RuntimeError, match="not an integer"):
        profile_module._integer(1.0, "field")
    with pytest.raises(RuntimeError, match="not numeric"):
        profile_module._number("1", "field")
    assert profile_module._canonical_python_ast(b"x=1\r\n") == (
        profile_module._canonical_python_ast(b"x=1\n")
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "patient_cluster_joint_vs_global_median_gain_90_interval",
            (0.1,),
            "two bounds",
        ),
        ("outer_loading_cosine_minima", (0.99,) * 8, "nine entries"),
    ],
)
def test_profile_evaluation_rejects_shape_drift(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
    message: str,
) -> None:
    fitted = neftel_program_fitted_catalog()
    evaluation = dict(fitted.evaluation)
    evaluation[field] = value
    drifted = replace(fitted, evaluation=evaluation)
    monkeypatch.setattr(profile_module, "neftel_program_fitted_catalog", lambda: drifted)
    with pytest.raises(RuntimeError, match=message):
        profile_module._evaluation_summary()


def test_profile_rejects_runtime_and_artifact_identity_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fitted = neftel_program_fitted_catalog()
    monkeypatch.setattr(np, "__version__", "0.0")
    with pytest.raises(RuntimeError, match="requires NumPy"):
        algorithm_profile()
    monkeypatch.setattr(np, "__version__", EXPECTED_NUMPY_VERSION)

    cases = (
        (replace(fitted, numpy_version="0.0"), "NumPy version"),
        (replace(fitted, profile_id="wrong-profile"), "profile identifier"),
        (replace(fitted, model_id="wrong-model"), "model identifier"),
    )
    for drifted, message in cases:
        monkeypatch.setattr(
            profile_module,
            "neftel_program_fitted_catalog",
            lambda drifted=drifted: drifted,
        )
        with pytest.raises(RuntimeError, match=message):
            algorithm_profile()


def test_demo_rejects_empty_feature_inventory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(demo_module, "_REQUEST_GENE_PATTERN", re.compile(r"(?!)"))
    with pytest.raises(RuntimeError, match="outside its bound"):
        demo_module._demo_feature_indices()


def test_service_facade_delegates_both_operations(monkeypatch: pytest.MonkeyPatch) -> None:
    request = synthetic_demo_request()
    analyzed = object()
    verified = object()
    monkeypatch.setattr(
        service_module,
        "analyze_longitudinal_gbm_neftel_transition",
        lambda _request, *, cancellation=None: analyzed,
    )
    monkeypatch.setattr(
        service_module,
        "verify_longitudinal_gbm_neftel_transition_replay",
        lambda _verification, *, cancellation=None: verified,
    )
    facade = LongitudinalGbmNeftelTransitionService()
    assert facade.analyze(request) is analyzed
    assert facade.verify(object()) is verified  # type: ignore[arg-type]
