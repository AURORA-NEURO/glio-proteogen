"""Branch oracles for the complex-transition engine's fail-closed paths."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from glio_proteogen.research.longitudinal_gbm_complex_transition import demo, engine
from glio_proteogen.research.longitudinal_gbm_complex_transition.contracts import (
    AnalysisSupport,
    ComplexTransitionClassification,
    LongitudinalGbmComplexTransitionRequest,
    LongitudinalTimePoint,
    ProteinEvidenceState,
    ValueSemantics,
)
from glio_proteogen.research.longitudinal_gbm_complex_transition.errors import (
    ComplexTransitionInferenceError,
)
from glio_proteogen.research.longitudinal_gbm_complex_transition.fitted_catalog import (
    ComplexTransitionFittedCatalog,
    FittedComplexModel,
    complex_transition_fitted_catalog,
)

if TYPE_CHECKING:
    from glio_proteogen.research.longitudinal_gbm_complex_transition.source_catalog import (
        ReactomeComplexBinding,
    )


def _context() -> tuple[
    LongitudinalGbmComplexTransitionRequest,
    ComplexTransitionFittedCatalog,
    FittedComplexModel,
    ReactomeComplexBinding,
    tuple[engine._ActiveMember, ...],
]:
    request = demo.synthetic_demo_request().model_copy(update={"bootstrap_replicates": 32})
    catalog = complex_transition_fitted_catalog()
    model = catalog.complexes[0]
    source = catalog.source_catalog.complexes[0]
    active = engine._active_members(request, 0, model, catalog)
    assert len(active) >= 3
    return request, catalog, model, source, active


def test_scalar_and_fitted_metadata_guards_fail_closed() -> None:
    _, catalog, _, _, _ = _context()

    with pytest.raises(ComplexTransitionInferenceError, match="non-finite"):
        engine._quantize(float("nan"))
    assert engine._sample_variance(()) == 0.0
    with pytest.raises(ComplexTransitionInferenceError, match="quantile"):
        engine._quantile((), 0.5)
    assert engine._quantile((0.25,), 0.5) == 0.25
    assert engine._effective_sample_size((0.0, 0.0)) == 0.0
    with pytest.raises(ComplexTransitionInferenceError, match="not an object"):
        engine._mapping([], "bad")
    with pytest.raises(ComplexTransitionInferenceError, match="not numeric"):
        engine._number("1", "bad")
    with pytest.raises(ComplexTransitionInferenceError, match="non-finite"):
        engine._number(float("inf"), "bad")

    malformed = replace(
        catalog,
        evaluation={
            "patient_cluster_bootstrap": {"nominal_90_percent_interval": [0.1]},
        },
    )
    with pytest.raises(ComplexTransitionInferenceError, match="gain interval is malformed"):
        engine._source_gain_interval(malformed)


def test_assay_profile_comparison_rejects_a_non_authoritative_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, catalog, _, _, _ = _context()
    foreign_profile = SimpleNamespace(required_assay_compatibility=object())
    monkeypatch.setattr(engine, "algorithm_profile", lambda: foreign_profile)

    with pytest.raises(ComplexTransitionInferenceError, match="assay attestation"):
        engine._validate_request(request, catalog)


def test_paired_censor_limits_are_uninformative_and_skipped() -> None:
    request, catalog, model, _, active = _context()
    observed = active[0].from_observation
    censored = observed.model_copy(update={"state": ProteinEvidenceState.LEFT_CENSORED})
    assert engine._pair_semantics(censored, censored) is None

    points: list[LongitudinalTimePoint] = []
    for point_index, point in enumerate(request.time_points[:2]):
        observations = tuple(
            item.model_copy(update={"state": ProteinEvidenceState.LEFT_CENSORED})
            for item in point.observations
        )
        points.append(
            LongitudinalTimePoint(
                time_point_id=f"paired-censor-{point_index}",
                time_offset_days=point.time_offset_days,
                normalization_reference_digest=point.normalization_reference_digest,
                observations=observations,
            )
        )
    censored_request = LongitudinalGbmComplexTransitionRequest(
        series_id="paired-censor-coverage",
        assay_compatibility=request.assay_compatibility,
        normalization_reference=request.normalization_reference,
        time_points=tuple(points),
        bootstrap_replicates=32,
    )

    assert engine._active_members(censored_request, 0, model, catalog) == ()


def test_failed_bootstrap_solve_is_counted_not_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, catalog, model, _, active = _context()
    monkeypatch.setattr(engine, "_solve", lambda *args, **kwargs: None)

    bootstrap = engine._bootstrap_coordinates(
        active,
        model,
        catalog,
        replicates=1,
        seed_digest="sha256:" + "1" * 64,
        cancellation=None,
    )

    assert bootstrap.failed_replicates == 1
    assert bootstrap.successful_replicates == 0


def test_zero_member_contribution_is_omitted() -> None:
    _, _, model, _, active = _context()
    exact = next(item for item in active if item.semantics is ValueSemantics.EXACT_DELTA)
    zero = replace(exact, raw_delta=0.0)

    assert engine._contributions((zero,), model) == ()


def test_nonpositive_source_gain_limits_support() -> None:
    _, catalog, model, source, _ = _context()
    stable_model = replace(
        model,
        evaluation=replace(
            model.evaluation,
            minimum_loading_cosine=1.0,
            relative_mae_gain_vs_training_center=0.1,
        ),
    )
    independent_source = replace(
        source,
        selected_parent_complex_ids=(),
        selected_child_complex_ids=(),
        same_family_max_eligible_jaccard=0.0,
    )
    nonpositive_gain = replace(
        catalog,
        evaluation={
            "patient_cluster_bootstrap": {
                "nominal_90_percent_interval": [-0.01, 0.2],
            },
        },
    )

    support, reasons = engine._support(
        ComplexTransitionClassification.STABLE,
        1.0,
        stable_model,
        independent_source,
        nonpositive_gain,
    )

    assert support is AnalysisSupport.LIMITED
    assert reasons == ("the source-panel patient-cluster gain interval crosses zero",)


def test_failed_point_solve_abstains(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, catalog, model, source, _ = _context()
    monkeypatch.setattr(engine, "_solve", lambda *args, **kwargs: None)

    result = engine._infer_complex(
        request,
        0,
        model=model,
        source=source,
        catalog=catalog,
        seed_digest="sha256:" + "2" * 64,
        cancellation=None,
    )

    assert result.support is AnalysisSupport.ABSTAINED
    assert result.limitations == ("robust member-coordinate solve did not converge monotonically",)


def test_insufficient_successful_bootstraps_abstains(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, catalog, model, source, _ = _context()
    failed = engine._BootstrapCoordinates(
        measurement=(),
        fitted_model=(),
        combined=(),
        failed_replicates=32,
    )
    monkeypatch.setattr(engine, "_bootstrap_coordinates", lambda *args, **kwargs: failed)

    result = engine._infer_complex(
        request,
        0,
        model=model,
        source=source,
        catalog=catalog,
        seed_digest="sha256:" + "3" * 64,
        cancellation=None,
    )

    assert result.support is AnalysisSupport.ABSTAINED
    assert result.limitations == ("fewer than 32 deterministic perturbation replicates converged",)


def test_synthetic_demo_inventory_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    demo.synthetic_demo_request.cache_clear()
    monkeypatch.setattr(demo, "_feature_domain_effects", dict)
    try:
        with pytest.raises(RuntimeError, match="feature inventory"):
            demo.synthetic_demo_request()
    finally:
        demo.synthetic_demo_request.cache_clear()
