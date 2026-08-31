from __future__ import annotations

import math
from collections import Counter
from dataclasses import replace
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import numpy as np
import pytest

from glio_proteogen.research.longitudinal_gbm_neftel_transition import engine
from glio_proteogen.research.longitudinal_gbm_neftel_transition.contracts import (
    AnalysisSupport,
    ConditionalProgramAblations,
    ConditionalTransitionClassification,
    GlobalTransitionClassification,
    GlobalTransitionConcordance,
    LongitudinalGbmNeftelTransitionRequest,
    ProteinEvidenceState,
    ProteinObservation,
)
from glio_proteogen.research.longitudinal_gbm_neftel_transition.demo import (
    synthetic_demo_request,
)
from glio_proteogen.research.longitudinal_gbm_neftel_transition.errors import (
    NeftelConditionalInferenceError,
    NeftelConditionalModelIntegrityError,
)
from glio_proteogen.research.longitudinal_gbm_neftel_transition.fitted_catalog import (
    FittedProgramLoading,
    NeftelProgramFittedCatalog,
    neftel_program_fitted_catalog,
)
from glio_proteogen.research.longitudinal_gbm_neftel_transition.profile import (
    algorithm_profile,
)
from glio_proteogen.research.longitudinal_gbm_neftel_transition.solver import (
    BoundSemantics,
    ConditionalSolverDiagnostics,
    ConditionalSolveResult,
    SolverEvidence,
    solve_conditional_coordinates,
)
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
)

if TYPE_CHECKING:
    from numpy.typing import NDArray

    FloatMatrix = NDArray[np.float64]


_OVERLAP_ASSERTION = "demo requires supported overlapping Neftel program pair"
_FORCED_OVERLAP_FAILURE = "forced overlap failure"
_FORCED_TOP_FAILURE = "forced top-contribution failure"


def _invalid_result(
    *,
    coordinate_count: int = 1,
    converged: bool = False,
    monotone: bool = False,
    condition: float = math.inf,
    coordinate: float = 0.0,
) -> ConditionalSolveResult:
    return ConditionalSolveResult(
        coordinates=tuple(coordinate for _ in range(coordinate_count)),
        diagnostics=ConditionalSolverDiagnostics(
            converged=converged,
            iterations=1,
            final_max_coordinate_change=1.0,
            initial_objective=1.0,
            final_objective=1.0,
            objective_trace=(1.0,),
            objective_monotone=monotone,
            active_evidence_count=1,
            exact_evidence_count=1,
            upper_bound_count=0,
            lower_bound_count=0,
            design_condition_number=condition,
        ),
    )


def _valid_result(
    coordinate_count: int,
    *,
    coordinate: float = 0.1,
) -> ConditionalSolveResult:
    return ConditionalSolveResult(
        coordinates=tuple(coordinate for _ in range(coordinate_count)),
        diagnostics=ConditionalSolverDiagnostics(
            converged=True,
            iterations=2,
            final_max_coordinate_change=0.0,
            initial_objective=1.0,
            final_objective=0.5,
            objective_trace=(1.0, 0.5),
            objective_monotone=True,
            active_evidence_count=32,
            exact_evidence_count=32,
            upper_bound_count=0,
            lower_bound_count=0,
            design_condition_number=2.0,
        ),
    )


@pytest.mark.parametrize(
    ("design", "evidence", "message"),
    [
        (np.empty((0, 1)), (SolverEvidence(0, 0.0, "exact_delta", 1.0),), "non-empty"),
        (
            np.asarray([[math.nan]]),
            (SolverEvidence(0, 0.0, "exact_delta", 1.0),),
            "non-finite",
        ),
        (np.ones((1, 1)), (), "active evidence"),
        (
            np.ones((1, 1)),
            (
                SolverEvidence(0, 0.0, "exact_delta", 1.0),
                SolverEvidence(0, 0.1, "exact_delta", 1.0),
            ),
            "duplicated",
        ),
        (
            np.ones((1, 1)),
            (SolverEvidence(1, 0.0, "exact_delta", 1.0),),
            "out of range",
        ),
        (
            np.ones((1, 1)),
            (SolverEvidence(0, math.inf, "exact_delta", 1.0),),
            "finite",
        ),
        (
            np.ones((1, 1)),
            (SolverEvidence(0, 0.0, "exact_delta", 0.0),),
            "positive",
        ),
        (
            np.ones((1, 1)),
            (SolverEvidence(0, 0.0, cast("BoundSemantics", "invalid"), 1.0),),
            "unsupported",
        ),
    ],
)
def test_solver_rejects_invalid_inputs(
    design: FloatMatrix,
    evidence: tuple[SolverEvidence, ...],
    message: str,
) -> None:
    with pytest.raises(NeftelConditionalInferenceError, match=message):
        solve_conditional_coordinates(design, evidence)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"huber_k": 0.0},
        {"ridge_lambda": 0.0},
        {"global_ridge_multiplier": 0.0},
        {"damping": 0.0},
        {"damping": 1.1},
        {"max_iterations": 0},
        {"tolerance": 0.0},
    ],
)
def test_solver_rejects_invalid_constants(kwargs: dict[str, float | int]) -> None:
    with pytest.raises(NeftelConditionalInferenceError, match="outside their domain"):
        solve_conditional_coordinates(
            np.ones((1, 1), dtype=np.float64),
            (SolverEvidence(0, 0.0, "exact_delta", 1.0),),
            **kwargs,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("initial", [(0.0, 0.0), (math.nan,)])
def test_solver_rejects_invalid_warm_start(initial: tuple[float, ...]) -> None:
    with pytest.raises(NeftelConditionalInferenceError, match="initial coordinates"):
        solve_conditional_coordinates(
            np.ones((1, 1), dtype=np.float64),
            (SolverEvidence(0, 0.0, "exact_delta", 1.0),),
            initial_coordinates=initial,
        )


def test_solver_nonconvergence_condition_and_linear_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = solve_conditional_coordinates(
        np.eye(2, dtype=np.float64),
        (
            SolverEvidence(0, 2.0, "exact_delta", 1.0),
            SolverEvidence(1, -2.0, "exact_delta", 1.0),
        ),
        max_iterations=1,
        tolerance=1.0e-30,
    )
    assert not result.diagnostics.converged
    collinear = solve_conditional_coordinates(
        np.ones((2, 2), dtype=np.float64),
        (
            SolverEvidence(0, 1.0, "exact_delta", 1.0),
            SolverEvidence(1, 1.0, "exact_delta", 1.0),
        ),
    )
    assert math.isinf(collinear.diagnostics.design_condition_number)

    monkeypatch.setattr(
        np.linalg,
        "solve",
        lambda *_: (_ for _ in ()).throw(np.linalg.LinAlgError()),
    )
    with pytest.raises(NeftelConditionalInferenceError, match="singular"):
        solve_conditional_coordinates(
            np.ones((1, 1), dtype=np.float64),
            (SolverEvidence(0, 1.0, "exact_delta", 1.0),),
        )
    monkeypatch.setattr(np.linalg, "solve", lambda *_: np.asarray([math.inf]))
    with pytest.raises(NeftelConditionalInferenceError, match="non-finite"):
        solve_conditional_coordinates(
            np.ones((1, 1), dtype=np.float64),
            (SolverEvidence(0, 1.0, "exact_delta", 1.0),),
        )


def test_solver_honors_cancellation() -> None:
    cancellation = CancellationContext()
    cancellation.cancel()
    with pytest.raises(InferenceCancelledError):
        solve_conditional_coordinates(
            np.ones((1, 1), dtype=np.float64),
            (SolverEvidence(0, 1.0, "exact_delta", 1.0),),
            cancellation=cancellation,
        )


def _two_point_demo() -> LongitudinalGbmNeftelTransitionRequest:
    source = synthetic_demo_request()
    return source.model_copy(
        update={"time_points": source.time_points[:2], "bootstrap_replicates": 32}
    )


def _unknown_active_request() -> LongitudinalGbmNeftelTransitionRequest:
    demo = _two_point_demo()
    points = tuple(
        point.model_copy(
            update={
                "observations": (
                    *point.observations[:2],
                    ProteinObservation(
                        observation_id=f"unknown.active.{index}",
                        gene_symbol="NOTAREALGENE",
                        state=ProteinEvidenceState.OBSERVED,
                        log_abundance=1.0 + index,
                        standard_error=0.1,
                        quality_weight=1.0,
                        provenance_digest="sha256:" + "a" * 64,
                    ),
                )
            }
        )
        for index, point in enumerate(demo.time_points)
    )
    return demo.model_copy(update={"series_id": "unknown.active.neftel", "time_points": points})


def _missing_request() -> LongitudinalGbmNeftelTransitionRequest:
    demo = _two_point_demo()
    template = demo.time_points[0].observations[0]
    points = tuple(
        point.model_copy(
            update={
                "observations": (
                    ProteinObservation(
                        observation_id=f"missing.{index}",
                        gene_symbol=template.gene_symbol,
                        state=ProteinEvidenceState.MISSING,
                        log_abundance=None,
                        standard_error=None,
                        quality_weight=0.0,
                        provenance_digest=template.provenance_digest,
                    ),
                )
            }
        )
        for index, point in enumerate(demo.time_points)
    )
    return demo.model_copy(update={"series_id": "neftel.missing.only", "time_points": points})


def test_engine_numeric_and_classification_boundaries() -> None:
    with pytest.raises(NeftelConditionalInferenceError, match="non-finite"):
        engine._quantize(math.inf)
    assert engine._probability(-1.0) == 0.0
    assert engine._probability(2.0) == 1.0
    assert engine._sample_standard_deviation((1.0,)) == 0.0
    with pytest.raises(NeftelConditionalInferenceError, match="different lengths"):
        engine._sample_covariance((1.0,), ())
    assert engine._sample_covariance((1.0,), (2.0,)) == 0.0
    with pytest.raises(NeftelConditionalInferenceError, match="requires fitted values"):
        engine._quantile((), 0.5)
    assert engine._quantile((3.0,), 0.5) == 3.0
    assert engine._effective_sample_size(()) == 0.0
    assert engine._effective_sample_size((0.0, 0.0)) == 0.0

    assert engine._global_classification(0.26, 0.5) is (
        GlobalTransitionClassification.SOURCE_LATER_TIMEPOINT_ALIGNED
    )
    assert engine._global_classification(-0.5, -0.26) is (
        GlobalTransitionClassification.SOURCE_EARLIER_TIMEPOINT_ALIGNED
    )
    assert engine._global_classification(-0.25, 0.25) is GlobalTransitionClassification.STABLE
    assert engine._global_classification(-0.3, 0.3) is (
        GlobalTransitionClassification.INDETERMINATE
    )
    assert engine._program_classification(0.26, 0.5) is (
        ConditionalTransitionClassification.CONDITIONAL_SOURCE_LATER_TIMEPOINT_ALIGNED
    )
    assert engine._program_classification(-0.5, -0.26) is (
        ConditionalTransitionClassification.CONDITIONAL_SOURCE_EARLIER_TIMEPOINT_ALIGNED
    )
    assert engine._program_classification(-0.25, 0.25) is (
        ConditionalTransitionClassification.CONDITIONALLY_STABLE
    )
    assert engine._program_classification(-0.3, 0.3) is (
        ConditionalTransitionClassification.INDETERMINATE
    )
    assert engine._point_program_classification(0.3) is (
        ConditionalTransitionClassification.CONDITIONAL_SOURCE_LATER_TIMEPOINT_ALIGNED
    )
    assert engine._point_program_classification(-0.3) is (
        ConditionalTransitionClassification.CONDITIONAL_SOURCE_EARLIER_TIMEPOINT_ALIGNED
    )


def test_solve_validity_short_circuits_every_gate() -> None:
    assert not engine._solve_is_valid(_invalid_result())
    assert not engine._solve_is_valid(
        _invalid_result(converged=True, monotone=False, condition=2.0)
    )
    assert not engine._solve_is_valid(
        _invalid_result(converged=True, monotone=True, condition=math.inf)
    )
    assert not engine._solve_is_valid(
        _invalid_result(
            converged=True,
            monotone=True,
            condition=2.0,
            coordinate=math.nan,
        )
    )
    assert engine._solve_is_valid(_valid_result(1))


def test_engine_rejects_unknown_assay_and_unknown_active_gene(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = neftel_program_fitted_catalog()
    demo = _two_point_demo()
    monkeypatch.setattr(
        engine,
        "algorithm_profile",
        lambda: SimpleNamespace(required_assay_compatibility=object()),
    )
    with pytest.raises(NeftelConditionalInferenceError, match="assay attestation"):
        engine._validate_request(demo, catalog)
    monkeypatch.undo()
    with pytest.raises(NeftelConditionalInferenceError, match="outside the locked"):
        engine.infer_longitudinal_gbm_neftel_transition(_unknown_active_request())

    cancellation = CancellationContext()
    cancellation.cancel()
    with pytest.raises(InferenceCancelledError):
        engine.infer_longitudinal_gbm_neftel_transition(demo, cancellation=cancellation)


def test_active_pair_semantics_and_outside_panel_are_conservative() -> None:
    request = _two_point_demo()
    catalog = neftel_program_fitted_catalog()
    source_index = next(
        index
        for index in range(len(catalog.source_catalog.genes))
        if index not in catalog.local_index_by_feature
    )
    symbol = catalog.source_catalog.genes[source_index]
    template = request.time_points[0].observations[0]
    outside_points = tuple(
        point.model_copy(
            update={
                "observations": (
                    template.model_copy(
                        update={
                            "observation_id": f"outside.panel.{index}",
                            "gene_symbol": symbol,
                        }
                    ),
                )
            }
        )
        for index, point in enumerate(request.time_points)
    )
    outside = request.model_copy(
        update={"series_id": "outside.panel", "time_points": outside_points}
    )
    assert engine._active_pairs(outside, 0, catalog) == ()

    left_template = request.time_points[0].observations[1]
    right_template = request.time_points[1].observations[1]
    left = request.time_points[0].model_copy(
        update={
            "observations": (
                left_template.model_copy(update={"state": ProteinEvidenceState.LEFT_CENSORED}),
            )
        }
    )
    right = request.time_points[1].model_copy(update={"observations": (right_template,)})
    lower = request.model_copy(update={"time_points": (left, right)})
    assert engine._active_pairs(lower, 0, catalog)[0].semantics == "lower_bound"


def _bootstrap_rows(
    coordinate_count: int,
    count: int,
    *,
    coordinate: float = 0.1,
    failures: int = 0,
) -> engine._BootstrapCoordinates:
    rows = tuple(tuple(coordinate for _ in range(coordinate_count)) for _ in range(count))
    return engine._BootstrapCoordinates(
        measurement=rows,
        fitted_model=rows,
        combined=rows,
        selected_row_digests=tuple(f"row.{index}" for index in range(count)),
        failed_replicates=failures,
    )


def test_bootstrap_failures_and_global_limitations_are_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _two_point_demo()
    catalog = neftel_program_fitted_catalog()
    active = engine._active_pairs(request, 0, catalog)
    monkeypatch.setattr(
        engine,
        "solve_conditional_coordinates",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(NeftelConditionalInferenceError("forced")),
    )
    failed = engine._bootstrap_coordinates(
        active,
        catalog,
        "sha256:" + "b" * 64,
        0,
        1,
        cancellation=None,
    )
    assert failed.successful_replicates == 0
    assert failed.failed_replicates == 1

    monkeypatch.setattr(
        engine, "solve_conditional_coordinates", lambda *_a, **_k: _invalid_result()
    )
    invalid = engine._bootstrap_coordinates(
        active,
        catalog,
        "sha256:" + "c" * 64,
        0,
        1,
        cancellation=None,
    )
    assert invalid.successful_replicates == 0
    assert invalid.failed_replicates == 1

    metrics = engine._MassMetrics(16, 16, 16, 0, 0, 1.0, 8.0)
    limited = engine._global_result(
        _valid_result(1),
        _bootstrap_rows(1, 32, failures=1),
        metrics,
        1.0,
    )
    assert limited.support is AnalysisSupport.LIMITED
    assert "not estimable" in " ".join(limited.abstention_reasons)


def test_bootstrap_selection_honors_256_with_balanced_independent_rounds() -> None:
    catalog = neftel_program_fitted_catalog()
    seed = "sha256:" + "d" * 64
    selected = engine._selected_draw_indices(catalog, seed, 256)

    assert len(selected) == 256
    assert Counter(selected) == Counter(dict.fromkeys(range(128), 2))
    assert selected == engine._selected_draw_indices(catalog, seed, 256)
    assert selected != engine._selected_draw_indices(catalog, "sha256:" + "e" * 64, 256)
    assert engine._selected_draw_indices(catalog, seed, 0) == ()

    active = engine._active_pairs(_two_point_demo(), 0, catalog)
    row_digest = catalog.bootstrap_row_digests[selected[0]]
    first = engine._perturbed_deltas(active, seed, 0, 0, row_digest)
    repeated_source = engine._perturbed_deltas(active, seed, 0, 128, row_digest)
    assert not np.array_equal(first, repeated_source)


def test_bootstrap_selection_rejects_an_empty_source_ensemble() -> None:
    catalog = neftel_program_fitted_catalog()
    empty = replace(
        catalog,
        bootstrap_scales=np.empty((0, catalog.union_feature_count), dtype=np.float32),
        bootstrap_effects=np.empty((0, catalog.union_feature_count), dtype=np.float32),
        bootstrap_row_digests=(),
    )
    with pytest.raises(NeftelConditionalModelIntegrityError, match="no source-bootstrap"):
        engine._selected_draw_indices(empty, "sha256:" + "f" * 64, 1)


def test_binding_censor_detection_uses_signed_one_sided_slack() -> None:
    catalog = neftel_program_fitted_catalog()
    pair = engine._active_pairs(_two_point_demo(), 0, catalog)[0]
    coordinates = np.zeros(catalog.program_count + 1, dtype=np.float64)

    exact = replace(pair, semantics="exact_delta", raw_delta=100.0)
    assert engine._bound_is_informative(exact, 1.0, catalog.reference_design, coordinates)
    assert engine._bound_is_informative(
        replace(pair, semantics="upper_bound", raw_delta=-1.0),
        1.0,
        catalog.reference_design,
        coordinates,
    )
    assert not engine._bound_is_informative(
        replace(pair, semantics="upper_bound", raw_delta=1.0),
        1.0,
        catalog.reference_design,
        coordinates,
    )
    assert engine._bound_is_informative(
        replace(pair, semantics="lower_bound", raw_delta=1.0),
        1.0,
        catalog.reference_design,
        coordinates,
    )
    assert not engine._bound_is_informative(
        replace(pair, semantics="lower_bound", raw_delta=-1.0),
        1.0,
        catalog.reference_design,
        coordinates,
    )


def test_empty_failed_and_invalid_ablation_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = neftel_program_fitted_catalog()
    program = catalog.programs[0]
    empty = engine._solve_ablation(
        (),
        catalog.reference_scale,
        catalog.reference_design,
        1,
        program.cross_fitted_mad_scale,
        "source_processing",
        "empty",
        0.0,
        cancellation=None,
    )
    assert empty.support is AnalysisSupport.ABSTAINED

    active = engine._active_pairs(_two_point_demo(), 0, catalog)
    monkeypatch.setattr(
        engine,
        "solve_conditional_coordinates",
        lambda *_a, **_k: (_ for _ in ()).throw(NeftelConditionalInferenceError("forced")),
    )
    failed = engine._solve_ablation(
        active,
        catalog.reference_scale,
        catalog.reference_design,
        1,
        program.cross_fitted_mad_scale,
        "source_processing",
        "failed",
        0.0,
        cancellation=None,
    )
    assert failed.support is AnalysisSupport.ABSTAINED
    monkeypatch.setattr(
        engine, "solve_conditional_coordinates", lambda *_a, **_k: _invalid_result()
    )
    invalid = engine._solve_ablation(
        active,
        catalog.reference_scale,
        catalog.reference_design,
        1,
        program.cross_fitted_mad_scale,
        "source_processing",
        "invalid",
        0.0,
        cancellation=None,
    )
    assert invalid.support is AnalysisSupport.ABSTAINED


def _overlap_pair(
    active: tuple[engine._ActivePair, ...],
    catalog: NeftelProgramFittedCatalog,
) -> tuple[FittedProgramLoading, FittedProgramLoading, tuple[int, ...]]:
    for left_index, left in enumerate(catalog.programs):
        for right in catalog.programs[left_index + 1 :]:
            shared = frozenset(left.member_local_indices) & frozenset(right.member_local_indices)
            removed = tuple(pair.local_position for pair in active if pair.local_position in shared)
            if not removed:
                continue
            remaining = tuple(pair for pair in active if pair.local_position not in shared)
            if all(
                (
                    (
                        metrics := engine._mass_metrics(
                            remaining,
                            item.unadjusted_loading,
                            item.member_local_indices,
                            catalog.reference_scale,
                        )
                    ).active_count
                    >= 5
                    and metrics.coverage >= 0.5
                    and metrics.effective_sample_size >= 3.0
                )
                for item in (left, right)
            ):
                return left, right, tuple(sorted(removed))
    raise AssertionError(_OVERLAP_ASSERTION)


def test_overlap_support_gate_abstains_after_refit(monkeypatch: pytest.MonkeyPatch) -> None:
    catalog = neftel_program_fitted_catalog()
    active = engine._active_pairs(_two_point_demo(), 0, catalog)
    left, right, removed_positions = _overlap_pair(active, catalog)
    shared_only = tuple(pair for pair in active if pair.local_position in removed_positions)
    small_catalog = replace(catalog, programs=(left, right))
    monkeypatch.setattr(
        engine,
        "solve_conditional_coordinates",
        lambda design, *_a, **_k: _valid_result(design.shape[1]),
    )
    result = engine._program_ablations(
        shared_only,
        small_catalog,
        left,
        0.2,
        {},
        cancellation=None,
    )
    assert result.overlap[0].support is AnalysisSupport.ABSTAINED
    assert "informative-evidence gates" in cast("str", result.overlap[0].reason)


@pytest.mark.parametrize("outcome", ["error", "invalid", "valid"])
def test_overlap_refit_is_cached_and_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
) -> None:
    catalog = neftel_program_fitted_catalog()
    active = engine._active_pairs(_two_point_demo(), 0, catalog)
    left, right, removed_positions = _overlap_pair(active, catalog)
    small_catalog = replace(catalog, programs=(left, right))
    remaining_positions = frozenset(
        pair.local_position for pair in active if pair.local_position not in removed_positions
    )
    overlap_calls = 0

    def controlled_solver(
        design: FloatMatrix,
        evidence: tuple[SolverEvidence, ...],
        **_kwargs: object,
    ) -> ConditionalSolveResult:
        nonlocal overlap_calls
        positions = frozenset(item.feature_position for item in evidence)
        if positions == remaining_positions and design.shape == catalog.reference_design.shape:
            overlap_calls += 1
            if outcome == "error":
                raise NeftelConditionalInferenceError(_FORCED_OVERLAP_FAILURE)
            if outcome == "invalid":
                return _invalid_result(coordinate_count=design.shape[1], condition=2.0)
        return _valid_result(design.shape[1])

    monkeypatch.setattr(engine, "solve_conditional_coordinates", controlled_solver)
    cache: dict[tuple[int, ...], ConditionalSolveResult | None] = {}
    left_result = engine._program_ablations(
        active,
        small_catalog,
        left,
        0.4,
        cache,
        cancellation=None,
    )
    right_result = engine._program_ablations(
        active,
        small_catalog,
        right,
        0.4,
        cache,
        cancellation=None,
    )
    assert overlap_calls == 1
    expected = AnalysisSupport.LIMITED if outcome == "valid" else AnalysisSupport.ABSTAINED
    assert left_result.overlap[0].support is expected
    assert right_result.overlap[0].support is expected


@pytest.mark.parametrize("outcome", ["error", "invalid"])
def test_top_contribution_refits_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
) -> None:
    catalog = neftel_program_fitted_catalog()
    active = engine._active_pairs(_two_point_demo(), 0, catalog)
    program = catalog.programs[0]
    removed = next(pair for pair in active if pair.semantics == "exact_delta")
    all_positions = frozenset(pair.local_position for pair in active)

    def controlled_solver(
        design: FloatMatrix,
        evidence: tuple[SolverEvidence, ...],
        **_kwargs: object,
    ) -> ConditionalSolveResult:
        positions = frozenset(item.feature_position for item in evidence)
        is_target_omission = (
            removed.local_position not in positions
            and len(positions) == len(all_positions) - 1
            and design.shape == catalog.reference_design.shape
        )
        if is_target_omission and outcome == "error":
            raise NeftelConditionalInferenceError(_FORCED_TOP_FAILURE)
        if is_target_omission:
            return _invalid_result(coordinate_count=design.shape[1], condition=2.0)
        return _valid_result(design.shape[1])

    monkeypatch.setattr(engine, "solve_conditional_coordinates", controlled_solver)
    result = engine._program_ablations(
        active,
        catalog,
        program,
        0.2,
        {},
        point_coordinates=tuple(0.0 for _ in range(catalog.program_count + 1)),
        top_contribution_pairs=((removed.gene_symbol, removed.local_position),),
        cancellation=None,
    )
    top = result.top_contributions[0]
    assert top.support is AnalysisSupport.ABSTAINED
    assert "refit" in cast("str", top.reason)


@pytest.mark.parametrize(
    "outcome",
    ["full_error", "full_invalid", "omitted_error", "omitted_invalid"],
)
def test_request_reconstruction_failures_are_not_evaluable(
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
) -> None:
    catalog = neftel_program_fitted_catalog()
    active = engine._active_pairs(_two_point_demo(), 0, catalog)

    def controlled_solver(
        design: FloatMatrix,
        *_args: object,
        **_kwargs: object,
    ) -> ConditionalSolveResult:
        full = design.shape[1] == catalog.reference_design.shape[1]
        if (outcome == "full_error" and full) or (outcome == "omitted_error" and not full):
            raise NeftelConditionalInferenceError("forced")
        if (outcome == "full_invalid" and full) or (outcome == "omitted_invalid" and not full):
            return _invalid_result(coordinate_count=design.shape[1], condition=2.0)
        return _valid_result(design.shape[1])

    monkeypatch.setattr(engine, "solve_conditional_coordinates", controlled_solver)
    reconstruction = engine._request_reconstruction(active, catalog, cancellation=None)
    assert all(evaluable == 0 for evaluable, _improved, _gain in reconstruction)


def test_request_reconstruction_skips_empty_folds() -> None:
    catalog = neftel_program_fitted_catalog()
    assert engine._request_reconstruction((), catalog, cancellation=None) == tuple(
        (0, 0, 0.0) for _ in catalog.programs
    )


def test_contribution_and_discordance_filters_do_not_invent_signal() -> None:
    catalog = neftel_program_fitted_catalog()
    active = engine._active_pairs(_two_point_demo(), 0, catalog)
    program = catalog.programs[0]
    low_quality = tuple(replace(pair, quality_weight=1.0e-12) for pair in active)
    assert engine._top_contributions(low_quality, program, catalog.reference_scale) == ()
    assert engine._discordance(low_quality, program, catalog.reference_scale, 1.0) == 0.0

    zeros = np.zeros(catalog.union_feature_count, dtype=np.float64)
    zero_program = replace(
        program,
        unadjusted_loading=zeros,
        global_adjustment_loading=zeros,
        conditional_loading=zeros,
    )
    assert engine._top_contributions(active, zero_program, catalog.reference_scale) == ()
    assert 0.0 < engine._discordance(active, program, catalog.reference_scale, 0.0) <= 1.0
    assert engine._discordance(active, zero_program, catalog.reference_scale, 1.0) == 0.0
    metrics = engine._mass_metrics(
        active,
        zeros,
        program.member_local_indices,
        catalog.reference_scale,
    )
    assert metrics.coverage == 0.0


def _numeric_ablations(score: float) -> ConditionalProgramAblations:
    return ConditionalProgramAblations(
        global_axis=engine._numeric_ablation(
            "global_axis", "global_transition", score, score, "test sensitivity"
        ),
        source_processing=(
            engine._numeric_ablation(
                "source_processing", "ordinary", score, score, "test sensitivity"
            ),
        ),
        degree_normalization=engine._numeric_ablation(
            "degree_normalization", "degree", score, score, "test sensitivity"
        ),
        unique_members=engine._numeric_ablation(
            "unique_members", "unique", score, score, "test sensitivity"
        ),
        leave_program_out=engine._numeric_ablation(
            "leave_program_out", "leave", score, 0.0, "test sensitivity"
        ),
    )


def _estimable_global() -> GlobalTransitionConcordance:
    return engine._global_result(
        _valid_result(1),
        _bootstrap_rows(1, 64),
        engine._MassMetrics(16, 16, 16, 0, 0, 1.0, 8.0),
        1.0,
    )


def test_program_result_exposes_limited_runtime_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = neftel_program_fitted_catalog()
    active = engine._active_pairs(_two_point_demo(), 0, catalog)
    program = catalog.programs[0]
    monkeypatch.setattr(
        engine,
        "_program_ablations",
        lambda _active, _catalog, _program, score, _cache, **_kwargs: _numeric_ablations(score),
    )
    limited = engine._program_result(
        active,
        catalog,
        program,
        _valid_result(catalog.program_count + 1),
        _bootstrap_rows(catalog.program_count + 1, 32, failures=1),
        _estimable_global(),
        (4, 3, 0.0),
        {},
        cancellation=None,
    )
    reasons = " ".join(limited.abstention_reasons)
    assert limited.support is AnalysisSupport.LIMITED
    assert "requested fitted bootstrap" in reasons
    assert "all five" in reasons

    no_unique = replace(program, unique_member_local_indices=())
    sparse = engine._program_result(
        active,
        catalog,
        no_unique,
        _valid_result(catalog.program_count + 1),
        _bootstrap_rows(catalog.program_count + 1, 64),
        _estimable_global(),
        (5, 5, 0.02),
        {},
        cancellation=None,
    )
    sparse_reasons = " ".join(sparse.abstention_reasons)
    assert "active unique" in sparse_reasons
    assert "unique-member coefficient mass" in sparse_reasons

    abstained = engine._abstained_ablation(
        "source_processing",
        "ordinary",
        "forced structural failure",
    )
    structural_failure = _numeric_ablations(0.1).model_copy(
        update={"source_processing": (abstained,)}
    )
    monkeypatch.setattr(
        engine,
        "_program_ablations",
        lambda *_a, **_k: structural_failure,
    )
    structural = engine._program_result(
        active,
        catalog,
        program,
        _valid_result(catalog.program_count + 1),
        _bootstrap_rows(catalog.program_count + 1, 64),
        _estimable_global(),
        (5, 5, 0.02),
        {},
        cancellation=None,
    )
    assert "structural ablations" in " ".join(structural.abstention_reasons)


def test_primary_solve_failure_and_demo_oracle_mismatch_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = neftel_program_fitted_catalog()
    request = _two_point_demo()
    monkeypatch.setattr(
        engine,
        "solve_conditional_coordinates",
        lambda *_a, **_k: (_ for _ in ()).throw(
            NeftelConditionalInferenceError("forced primary failure")
        ),
    )
    failed = engine._calculate_transition(
        request,
        0,
        catalog,
        "sha256:" + "4" * 64,
        cancellation=None,
    )
    assert failed.global_transition.support is AnalysisSupport.ABSTAINED

    monkeypatch.undo()
    missing = _missing_request()
    profile = algorithm_profile().model_copy(update={"demo_request_digest": missing.request_digest})
    monkeypatch.setattr(engine, "algorithm_profile", lambda: profile)
    monkeypatch.setattr(
        engine,
        "EXPECTED_DEMO_SEMANTIC_ORACLE_DIGEST",
        "sha256:" + "0" * 64,
    )
    with pytest.raises(NeftelConditionalModelIntegrityError, match="semantic oracle"):
        engine.infer_longitudinal_gbm_neftel_transition(missing)
