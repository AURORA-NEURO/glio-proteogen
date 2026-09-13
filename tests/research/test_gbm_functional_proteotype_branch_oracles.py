"""Adversarial branch oracles for the GBM functional-proteotype core."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import replace
from typing import Any, cast

import numpy as np
import pytest
from pydantic import ValidationError

from glio_proteogen.research.gbm_functional_proteotype import (
    AblationKind,
    AnalysisSupport,
    AxisAblation,
    AxisClassification,
    AxisEvidence,
    AxisEvidenceCounts,
    FunctionalProteotypeAlgorithmConstants,
    FunctionalProteotypeProfile,
    FunctionalProteotypeProvenance,
    FunctionalProteotypeRequest,
    FunctionalProteotypeResult,
    LatentInterval,
    ObjectiveTraceStep,
    ProteinDriver,
    ProteinEvidence,
    ProteinEvidenceState,
    RankComparison,
    ReplayVerificationRequest,
    SolverDiagnostics,
    SolverTermination,
    SourceCohortPathwayContext,
    UnverifiedFunctionalProteotypeResult,
    algorithm_profile,
    analyze_functional_proteotype,
    synthetic_demo_request,
)
from glio_proteogen.research.gbm_functional_proteotype import catalog as catalog_module
from glio_proteogen.research.gbm_functional_proteotype import contracts as contracts_module
from glio_proteogen.research.gbm_functional_proteotype import engine as engine_module
from glio_proteogen.research.gbm_functional_proteotype import profile as profile_module
from glio_proteogen.research.gbm_functional_proteotype import service as service_module
from glio_proteogen.research.gbm_functional_proteotype import solver as solver_module
from glio_proteogen.research.gbm_functional_proteotype.canonical import (
    canonical_json_bytes,
    canonical_request_digest,
    objective_trace_digest,
    result_payload_digest,
)
from glio_proteogen.research.gbm_functional_proteotype.service import (
    FunctionalProteotypeService,
)
from glio_proteogen.research.gbm_functional_proteotype.solver import (
    SolverConfiguration,
    SolverObservation,
    SolverOutcome,
    objective,
    solve_constrained_latent,
)
from glio_proteogen.research.gbm_functional_proteotype.statistics import (
    average_ranks,
    benjamini_hochberg,
    mann_whitney_rank_statistic,
    rank_statistic_from_ranks,
    stratified_permutation_rank_test,
)

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


@pytest.fixture(scope="module")
def analyzed_demo() -> tuple[FunctionalProteotypeRequest, FunctionalProteotypeResult]:
    payload = synthetic_demo_request().model_dump(mode="json")
    payload["bootstrap_replicates"] = 16
    payload["permutation_replicates"] = 64
    request = FunctionalProteotypeRequest.model_validate_json(json.dumps(payload))
    return request, analyze_functional_proteotype(request)


def _catalog_document() -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(catalog_module._resource_bytes()))


def _counts(
    *,
    observed: int = 15,
    censored: int = 0,
    missing: int = 0,
    unsupported: int = 0,
    background: int = 45,
) -> AxisEvidenceCounts:
    declared = observed + censored + missing + unsupported
    return AxisEvidenceCounts(
        declared_signature_proteins=declared,
        observed_signature_proteins=observed,
        left_censored_signature_proteins=censored,
        missing_signature_proteins=missing,
        unsupported_signature_proteins=unsupported,
        unreported_signature_proteins=150 - declared,
        observed_background_proteins=background,
        active_signature_fraction=(observed + censored) / 150.0,
    )


def _rank(*, q_value: float = 0.05, rank_biserial: float = 0.6) -> RankComparison:
    return RankComparison(
        signature_observed_count=15,
        complement_observed_count=45,
        u_statistic=600.0,
        rank_biserial=rank_biserial,
        tie_correction=1.0,
        null_standard_deviation=0.1,
        empirical_p_value=0.04,
        q_value=q_value,
        permutation_replicates_used=64,
    )


def _configuration(**updates: object) -> SolverConfiguration:
    values: dict[str, object] = {
        "huber_delta": 1.345,
        "standard_error_floor": 0.25,
        "axis_ridge": 1e-4,
        "intercept_ridge": 1e-6,
        "damping": 1.0,
        "tolerance": 1e-8,
        "gradient_tolerance": 1e-7,
        "max_iterations": 16,
        "backtracking_factor": 0.5,
        "backtracking_steps": 8,
        "objective_increase_tolerance": 1e-12,
    }
    values.update(updates)
    return SolverConfiguration(**values)  # type: ignore[arg-type]


def _solver_observation(
    axis: int = 0,
    value: float = 1.0,
    *,
    state: str = "observed",
) -> SolverObservation:
    return SolverObservation(
        axis_index=axis,
        source_loading=1.0,
        state=state,  # type: ignore[arg-type]
        value=value,
        standard_error=0.3,
        quality_weight=0.9,
    )


def _outcome(*, converged: bool = True) -> SolverOutcome:
    return SolverOutcome(
        intercept=0.0,
        axis_values=(0.6, 0.2, -0.2, -0.6),
        converged=converged,
        iterations=0,
        objective=0.0,
        final_gradient_norm=0.0 if converged else 1.0,
        maximum_candidate_update=0.0,
        sum_to_zero_residual=0.0,
        objective_trace=(),
    )


def _valid_ablation_payload() -> dict[str, Any]:
    return {
        "kind": "top_driver",
        "target": "top_driver:CSTA",
        "proteins_removed": 1,
        "support_after_ablation": "supported",
        "baseline_estimate": 0.8,
        "ablated_estimate": 0.7,
        "estimate_delta": -0.1,
        "classification_after_ablation": "indeterminate",
        "reason": None,
    }


def test_active_evidence_requires_complete_finite_positive_values() -> None:
    gene = catalog_module.functional_proteotype_catalog().axes["GPM"][0].gene_symbol
    common = {
        "observation_id": "branch.active",
        "gene_symbol": gene,
        "state": "observed",
        "standardized_effect": 0.5,
        "standard_error": 0.3,
        "quality_weight": 0.9,
        "provenance_digest": DIGEST_A,
    }
    for updates, message in (
        ({"standardized_effect": None}, "require effect and error"),
        ({"standard_error": None}, "require effect and error"),
        ({"quality_weight": 0.0}, "require positive quality"),
    ):
        with pytest.raises(ValidationError, match=message):
            ProteinEvidence.model_validate_json(json.dumps({**common, **updates}))
    for field in ("standardized_effect", "standard_error", "quality_weight"):
        with pytest.raises(ValidationError):
            ProteinEvidence.model_validate_json(json.dumps({**common, field: math.nan}))


def test_request_rejects_duplicate_observation_ids_separately_from_gene_ids() -> None:
    rows = catalog_module.functional_proteotype_catalog().axes["GPM"][:2]
    observations = tuple(
        ProteinEvidence(
            observation_id="duplicate.id",
            gene_symbol=row.gene_symbol,
            state=ProteinEvidenceState.OBSERVED,
            standardized_effect=0.5,
            standard_error=0.3,
            quality_weight=0.9,
            provenance_digest=DIGEST_A,
        )
        for row in rows
    )
    with pytest.raises(ValidationError, match="observation identifiers must be unique"):
        FunctionalProteotypeRequest(
            sample_id="duplicate.request",
            observations=observations,
            bootstrap_replicates=16,
            permutation_replicates=64,
            effect_reference_id="reference",
        )


def test_inactive_evidence_cannot_cross_the_internal_solver_admission_guard() -> None:
    protein = catalog_module.functional_proteotype_catalog().axes["GPM"][0]
    inactive = ProteinEvidence(
        observation_id="inactive.guard",
        gene_symbol=protein.gene_symbol,
        state=ProteinEvidenceState.MISSING,
        quality_weight=0.0,
        provenance_digest=DIGEST_A,
    )
    mapped = engine_module._MappedObservation(
        evidence=inactive,
        protein=protein,
        axis_index=0,
    )
    with pytest.raises(AssertionError, match="only active evidence"):
        mapped.solver_observation()


def test_interval_rank_count_driver_and_pathway_contracts_fail_closed(
    analyzed_demo: tuple[FunctionalProteotypeRequest, FunctionalProteotypeResult],
) -> None:
    _request, result = analyzed_demo
    with pytest.raises(ValidationError, match="contain its estimate"):
        LatentInterval(
            estimate=0.5,
            lower_bound=0.6,
            upper_bound=0.8,
            bootstrap_replicates_used=16,
        )
    rank_payload = _rank().model_dump(mode="json")
    with pytest.raises(ValidationError, match="pairwise-comparison count"):
        RankComparison.model_validate({**rank_payload, "u_statistic": 676.0})
    with pytest.raises(ValidationError, match="cannot be smaller"):
        RankComparison.model_validate({**rank_payload, "empirical_p_value": 0.2, "q_value": 0.1})

    valid_counts = _counts().model_dump(mode="json")
    for updates, message in (
        ({"declared_signature_proteins": 14}, "state counts"),
        ({"unreported_signature_proteins": 134}, "cover the source signature"),
        ({"active_signature_fraction": 0.5}, "fraction must match"),
    ):
        with pytest.raises(ValidationError, match=message):
            AxisEvidenceCounts.model_validate({**valid_counts, **updates})

    driver = result.axis_evidence[0].top_drivers[0]
    driver_payload = driver.model_dump(mode="json")
    with pytest.raises(ValidationError, match="absolute contribution"):
        ProteinDriver.model_validate_json(
            json.dumps({**driver_payload, "absolute_contribution": 0.0})
        )
    with pytest.raises(ValidationError, match="active evidence"):
        ProteinDriver.model_validate_json(
            json.dumps(
                {
                    **driver_payload,
                    "evidence_state": "missing",
                    "value_role": "observed_point",
                }
            )
        )
    with pytest.raises(ValidationError, match="quartile"):
        ProteinDriver.model_validate_json(json.dumps({**driver_payload, "source_rank_quartile": 4}))

    context_payload = (
        result.axis_evidence[0].source_cohort_pathway_context[0].model_dump(mode="json")
    )
    with pytest.raises(ValidationError, match="q-value cannot be smaller"):
        SourceCohortPathwayContext.model_validate_json(
            json.dumps({**context_payload, "source_p_value": 0.2, "source_q_value": 0.1})
        )


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        (
            {
                "support_after_ablation": "abstained",
                "classification_after_ablation": "not_estimable",
                "reason": "insufficient",
            },
            "cannot carry an estimate",
        ),
        (
            {
                "support_after_ablation": "abstained",
                "baseline_estimate": None,
                "ablated_estimate": None,
                "estimate_delta": None,
                "classification_after_ablation": "source_aligned",
                "reason": "insufficient",
            },
            "must be not_estimable",
        ),
        (
            {
                "support_after_ablation": "abstained",
                "baseline_estimate": None,
                "ablated_estimate": None,
                "estimate_delta": None,
                "classification_after_ablation": "not_estimable",
                "reason": None,
            },
            "require a reason",
        ),
        ({"estimate_delta": None}, "require baseline, estimate, and delta"),
        ({"estimate_delta": 0.2}, "delta must equal"),
        (
            {"classification_after_ablation": "not_estimable"},
            "without bootstrap intervals must be indeterminate",
        ),
        (
            {"classification_after_ablation": "source_aligned"},
            "without bootstrap intervals must be indeterminate",
        ),
        (
            {"support_after_ablation": "limited", "reason": None},
            "limited ablations require a reason",
        ),
        ({"reason": "unexpected"}, "supported ablations cannot carry"),
    ],
)
def test_ablation_contract_rejects_incoherent_support_payloads(
    updates: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        AxisAblation.model_validate_json(json.dumps({**_valid_ablation_payload(), **updates}))


def test_interval_classification_predicate_covers_every_state() -> None:
    aligned = LatentInterval(
        estimate=0.5, lower_bound=0.3, upper_bound=0.7, bootstrap_replicates_used=16
    )
    opposed = LatentInterval(
        estimate=-0.5, lower_bound=-0.7, upper_bound=-0.3, bootstrap_replicates_used=16
    )
    neutral = LatentInterval(
        estimate=0.0, lower_bound=-0.2, upper_bound=0.2, bootstrap_replicates_used=16
    )
    indeterminate = LatentInterval(
        estimate=0.2, lower_bound=0.1, upper_bound=0.4, bootstrap_replicates_used=16
    )
    assert engine_module._classification_from_interval(0.3, 0.7) is (
        AxisClassification.SOURCE_ALIGNED
    )
    assert engine_module._classification_from_interval(-0.7, -0.3) is (
        AxisClassification.SOURCE_OPPOSED
    )
    assert engine_module._classification_from_interval(-0.2, 0.2) is AxisClassification.NEUTRAL
    assert engine_module._classification_from_interval(0.1, 0.4) is (
        AxisClassification.INDETERMINATE
    )
    assert engine_module._point_classification(0.0) is AxisClassification.NEUTRAL
    for classification, interval in (
        (AxisClassification.SOURCE_ALIGNED, aligned),
        (AxisClassification.SOURCE_OPPOSED, opposed),
        (AxisClassification.NEUTRAL, neutral),
        (AxisClassification.INDETERMINATE, indeterminate),
    ):
        assert contracts_module._classification_matches_interval(classification, interval)
    assert not contracts_module._classification_matches_interval(
        AxisClassification.NOT_ESTIMABLE,
        neutral,
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("driver_axis", "drivers must belong"),
        ("pathway_axis", "pathway contexts must belong"),
        ("duplicate_driver", "top-driver proteins must be unique"),
        ("duplicate_ablation", "ablation kind/target pairs must be unique"),
        ("estimated_without_latent", "estimated axes require a latent"),
        ("estimated_not_estimable", "estimated axes cannot be not_estimable"),
        ("classification_interval", "classification is not supported"),
        ("supported_with_reason", "supported axes cannot carry"),
        ("limited_without_reason", "limited axes require"),
        ("missing_ablation_family", "require all three ablation families"),
        ("abstained_classification", "abstained axes must be not_estimable"),
        ("abstained_estimate", "abstained axes cannot carry"),
        ("abstained_no_reason", "abstained axes require reasons"),
        ("abstained_ablation", "abstained axes cannot carry ablation"),
    ],
)
def test_axis_evidence_rejects_cross_axis_and_support_incoherence(  # noqa: C901, PLR0912
    analyzed_demo: tuple[FunctionalProteotypeRequest, FunctionalProteotypeResult],
    mutation: str,
    message: str,
) -> None:
    _request, result = analyzed_demo
    payload = result.axis_evidence[0].model_dump(mode="json")
    if mutation == "driver_axis":
        payload["top_drivers"][0]["axis"] = "MTC"
    elif mutation == "pathway_axis":
        payload["source_cohort_pathway_context"][0]["axis"] = "MTC"
    elif mutation == "duplicate_driver":
        payload["top_drivers"] = [payload["top_drivers"][0], payload["top_drivers"][0]]
    elif mutation == "duplicate_ablation":
        payload["ablations"] = [payload["ablations"][0], payload["ablations"][0]]
    elif mutation == "estimated_without_latent":
        payload["latent"] = None
    elif mutation == "estimated_not_estimable":
        payload["classification"] = "not_estimable"
    elif mutation == "classification_interval":
        payload["classification"] = "source_opposed"
    elif mutation == "supported_with_reason":
        payload["abstention_reasons"] = ["unexpected"]
    elif mutation == "limited_without_reason":
        payload["support"] = "limited"
    elif mutation == "missing_ablation_family":
        first_kind = payload["ablations"][0]["kind"]
        payload["ablations"] = [item for item in payload["ablations"] if item["kind"] != first_kind]
    elif mutation == "abstained_classification":
        payload["support"] = "abstained"
    else:
        payload.update(
            {
                "support": "abstained",
                "classification": "not_estimable",
                "latent": None,
                "rank": None,
                "top_drivers": [],
                "abstention_reasons": ["insufficient"],
                "ablations": [],
            }
        )
        if mutation == "abstained_estimate":
            payload["latent"] = cast(
                "LatentInterval",
                result.axis_evidence[0].latent,
            ).model_dump(mode="json")
        elif mutation == "abstained_no_reason":
            payload["abstention_reasons"] = []
        else:
            payload["ablations"] = [result.axis_evidence[0].ablations[0].model_dump(mode="json")]
    with pytest.raises(ValidationError, match=message):
        AxisEvidence.model_validate_json(json.dumps(payload))


def test_objective_trace_contract_checks_accepted_and_rejected_trials() -> None:
    valid = {
        "iteration": 1,
        "baseline_objective": 2.0,
        "candidate_objective": 1.0,
        "accepted_objective": 1.5,
        "damping": 0.5,
        "accepted": True,
    }
    with pytest.raises(ValidationError, match="positive damping"):
        ObjectiveTraceStep.model_validate({**valid, "damping": 0.0})
    with pytest.raises(ValidationError, match="cannot increase"):
        ObjectiveTraceStep.model_validate({**valid, "accepted_objective": 2.1})
    rejected = {
        **valid,
        "candidate_objective": 3.0,
        "accepted_objective": 2.0,
        "damping": 0.0,
        "accepted": False,
    }
    assert not ObjectiveTraceStep.model_validate(rejected).accepted
    with pytest.raises(ValidationError, match="preserve the baseline"):
        ObjectiveTraceStep.model_validate({**rejected, "accepted_objective": 1.9})


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("axis_order", "coordinates must contain"),
        ("coordinate_sum", "residual must equal"),
        ("iteration_count", "iteration count must equal"),
        ("trace_digest", "digest does not match"),
        ("initial_objective", "first trace baseline"),
        ("trace_chain", "continuous monotone chain"),
        ("final_objective", "final objective must match"),
        ("termination", "convergence flag and termination"),
        ("insufficient_iterations", "insufficient-evidence solve must not"),
    ],
)
def test_solver_diagnostics_rejects_forged_trace_semantics(
    analyzed_demo: tuple[FunctionalProteotypeRequest, FunctionalProteotypeResult],
    mutation: str,
    message: str,
) -> None:
    _request, result = analyzed_demo
    payload = result.solver.model_dump(mode="json")
    if mutation == "axis_order":
        payload["axis_coordinates"][0], payload["axis_coordinates"][1] = (
            payload["axis_coordinates"][1],
            payload["axis_coordinates"][0],
        )
    elif mutation == "coordinate_sum":
        payload["sum_to_zero_residual"] = 1e-7
    elif mutation == "iteration_count":
        payload["iterations"] += 1
    elif mutation == "trace_digest":
        payload["objective_trace_digest"] = DIGEST_A
    elif mutation == "initial_objective":
        payload["initial_objective"] += 1.0
    elif mutation == "trace_chain":
        payload["objective_trace"][1]["baseline_objective"] += 1.0
    elif mutation == "final_objective":
        payload["final_objective"] += 1.0
    elif mutation == "termination":
        payload["converged"] = False
    else:
        payload["converged"] = False
        payload["termination"] = "insufficient_evidence"
    if mutation == "trace_chain":
        payload["objective_trace_digest"] = objective_trace_digest(payload["objective_trace"])
    with pytest.raises(ValidationError, match=message):
        SolverDiagnostics.model_validate_json(json.dumps(payload))


def test_zero_iteration_solver_cannot_change_objective() -> None:
    diagnostics = engine_module._empty_diagnostics(SolverTermination.NUMERICAL_GUARD)
    payload = diagnostics.model_dump(mode="json")
    payload["final_objective"] = 0.1
    with pytest.raises(ValidationError, match="without iterations"):
        SolverDiagnostics.model_validate_json(json.dumps(payload))


def test_provenance_result_and_profile_content_digests_are_enforced(
    analyzed_demo: tuple[FunctionalProteotypeRequest, FunctionalProteotypeResult],
) -> None:
    _request, result = analyzed_demo
    provenance_payload = result.provenance.model_dump(mode="json")
    with pytest.raises(ValidationError, match="zero or at least 64"):
        FunctionalProteotypeProvenance.model_validate_json(
            json.dumps({**provenance_payload, "permutation_replicates_used": 1})
        )

    cases: tuple[tuple[str, str], ...] = (
        ("profile", "profile digest does not match provenance"),
        ("request", "request digest does not match provenance"),
        ("axis_order", "axis results must contain"),
        ("coordinate", "estimate must match"),
        ("digest", "result digest does not match"),
    )
    for case, message in cases:
        payload = result.model_dump(mode="json")
        if case == "profile":
            payload["profile_digest"] = DIGEST_A
        elif case == "request":
            payload["request_digest"] = DIGEST_A
        elif case == "axis_order":
            payload["axis_evidence"][0], payload["axis_evidence"][1] = (
                payload["axis_evidence"][1],
                payload["axis_evidence"][0],
            )
        elif case == "coordinate":
            latent = payload["axis_evidence"][0]["latent"]
            latent["estimate"] = latent["lower_bound"]
        else:
            payload["result_digest"] = DIGEST_A
        with pytest.raises(ValidationError, match=message):
            FunctionalProteotypeResult.model_validate_json(json.dumps(payload))

    constants = algorithm_profile().constants.model_dump(mode="json")
    for updates, message in (
        (
            {"initial_damping": 0.5, "minimum_damping": 0.75},
            "minimum damping cannot exceed",
        ),
        ({"minimum_damping": 0.1}, "must match the final deterministic"),
        (
            {
                "exploratory_minimum_active_proteins": 10,
                "supported_minimum_active_proteins": 5,
            },
            "cannot be weaker",
        ),
    ):
        with pytest.raises(ValidationError, match=message):
            FunctionalProteotypeAlgorithmConstants.model_validate({**constants, **updates})

    profile = algorithm_profile()
    for case, message in (
        ("axes", "profile axes must contain"),
        ("pathways", "pathway counts must reconcile"),
        ("digest", "profile digest does not match"),
    ):
        payload = profile.model_dump(mode="json")
        if case == "axes":
            payload["axes"][0], payload["axes"][1] = payload["axes"][1], payload["axes"][0]
        elif case == "pathways":
            payload["axes"][0]["pathway_count"] -= 1
        else:
            payload["profile_digest"] = DIGEST_B
        with pytest.raises(ValidationError, match=message):
            FunctionalProteotypeProfile.model_validate_json(json.dumps(payload))


def test_canonical_mapping_projection_and_unverified_result_remain_explicit(
    analyzed_demo: tuple[FunctionalProteotypeRequest, FunctionalProteotypeResult],
) -> None:
    request, result = analyzed_demo
    assert canonical_request_digest(request.model_dump(mode="json")) == request.request_digest
    assert result_payload_digest(result.model_dump(mode="json")) == result.result_digest
    unsigned = UnverifiedFunctionalProteotypeResult.model_validate_json(
        json.dumps({**result.model_dump(mode="json"), "result_digest": DIGEST_A})
    )
    assert unsigned.result_digest == DIGEST_A


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (b'{"a":1,"a":2}', "duplicate key"),
        (b'{"value":NaN}', "not strict JSON"),
        (b"{not-json", "not strict JSON"),
        (b"\xff", "not strict JSON"),
    ],
)
def test_catalog_parser_rejects_duplicate_nonfinite_or_invalid_json(
    raw: bytes,
    message: str,
) -> None:
    with pytest.raises(RuntimeError, match=message):
        catalog_module._plain_document(raw)


def test_catalog_parser_requires_object_and_typed_finite_fields() -> None:
    with pytest.raises(RuntimeError, match="root must be an object"):
        catalog_module._plain_document(b"[]")
    with pytest.raises(RuntimeError, match="must be numeric"):
        catalog_module._finite("1.0", field="score")
    with pytest.raises(RuntimeError, match="must be finite"):
        catalog_module._finite(math.inf, field="score")
    with pytest.raises(RuntimeError, match="non-empty text"):
        catalog_module._text("", field="gene")


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("axis_order", "axis order changed"),
        ("count", "signature size"),
        ("score", "scores are invalid or out of order"),
        ("rank", "ranks are not contiguous"),
        ("duplicate_gene", "gene symbols are not disjoint"),
    ],
)
def test_catalog_protein_inventory_rejects_semantic_tampering(case: str, message: str) -> None:
    document = _catalog_document()
    axes = cast("dict[str, list[dict[str, Any]]]", document["axes"])
    if case == "axis_order":
        document["axes"] = {
            "MTC": axes["MTC"],
            "GPM": axes["GPM"],
            "NEU": axes["NEU"],
            "PPR": axes["PPR"],
        }
    elif case == "count":
        axes["GPM"].pop()
    elif case == "score":
        axes["GPM"][0]["source_mww_score"] = 0.0
    elif case == "rank":
        axes["GPM"][0]["source_rank"] = 2
    else:
        axes["MTC"][0]["gene_symbol"] = axes["GPM"][0]["gene_symbol"]
    with pytest.raises(RuntimeError, match=message):
        catalog_module._protein_axes(document)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("axis_order", "pathway axis order changed"),
        ("count", "pathway-context size"),
        ("rank", "pathway ranks are not contiguous"),
        ("duplicate", "pathway context contains duplicates"),
        ("probability", "pathway probabilities are invalid"),
    ],
)
def test_catalog_pathway_inventory_rejects_semantic_tampering(
    case: str,
    message: str,
) -> None:
    document = _catalog_document()
    pathways = cast(
        "dict[str, list[dict[str, Any]]]",
        document["source_cohort_pathway_context"],
    )
    if case == "axis_order":
        document["source_cohort_pathway_context"] = {
            "MTC": pathways["MTC"],
            "GPM": pathways["GPM"],
            "NEU": pathways["NEU"],
            "PPR": pathways["PPR"],
        }
    elif case == "count":
        pathways["GPM"].pop()
    elif case == "rank":
        pathways["GPM"][0]["source_rank"] = 2
    elif case == "duplicate":
        pathways["GPM"][1]["pathway"] = pathways["GPM"][0]["pathway"]
    else:
        pathways["GPM"][0]["q_value"] = -0.1
    with pytest.raises(RuntimeError, match=message):
        catalog_module._pathway_context(document)


@pytest.mark.parametrize(
    ("constant", "replacement", "message"),
    [
        ("EXPECTED_SIGNATURE_CATALOG_DIGEST", DIGEST_A, "signature digest mismatch"),
        ("EXPECTED_PATHWAY_CATALOG_DIGEST", DIGEST_A, "pathway digest mismatch"),
        ("EXPECTED_AXIS_SIGNATURE_DIGESTS", {}, "per-axis signature digests changed"),
        ("EXPECTED_AXIS_PATHWAY_DIGESTS", {}, "per-axis pathway digests changed"),
        ("EXPECTED_SOURCE_SIZE_BYTES", 0, "source provenance changed"),
    ],
)
def test_catalog_top_level_locks_fail_before_tampered_evidence_is_admitted(
    monkeypatch: pytest.MonkeyPatch,
    constant: str,
    replacement: object,
    message: str,
) -> None:
    catalog_module.functional_proteotype_catalog.cache_clear()
    monkeypatch.setattr(catalog_module, constant, replacement)
    try:
        with pytest.raises(RuntimeError, match=message):
            catalog_module.functional_proteotype_catalog()
    finally:
        catalog_module.functional_proteotype_catalog.cache_clear()


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("schema", "unsupported .* schema"),
        ("content", "content digest mismatch"),
    ],
)
def test_catalog_rejects_digest_locked_schema_or_content_forgery(
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    message: str,
) -> None:
    document = _catalog_document()
    if case == "schema":
        document["schema_version"] = "unsupported/9.9.9"
    else:
        document["content_digest"] = DIGEST_A
    raw = canonical_json_bytes(document)
    monkeypatch.setattr(catalog_module, "_resource_bytes", lambda: raw)
    monkeypatch.setattr(
        catalog_module,
        "EXPECTED_ARTIFACT_DIGEST",
        "sha256:" + hashlib.sha256(raw).hexdigest(),
    )
    catalog_module.functional_proteotype_catalog.cache_clear()
    try:
        with pytest.raises(RuntimeError, match=message):
            catalog_module.functional_proteotype_catalog()
    finally:
        catalog_module.functional_proteotype_catalog.cache_clear()


def test_rank_primitives_reject_misaligned_nonfinite_and_degenerate_inputs() -> None:
    with pytest.raises(ValueError, match="finite one-dimensional"):
        average_ranks(np.asarray([[1.0, 2.0]], dtype=np.float64))
    with pytest.raises(ValueError, match="finite one-dimensional"):
        average_ranks(np.asarray([1.0, math.nan], dtype=np.float64))
    ranks = np.asarray([0.0, 1.0], dtype=np.float64)
    target = np.asarray([True, False], dtype=np.bool_)
    with pytest.raises(ValueError, match="aligned one-dimensional"):
        rank_statistic_from_ranks(ranks, target[:1])
    with pytest.raises(ValueError, match="rank vector must be finite"):
        rank_statistic_from_ranks(np.asarray([0.0, math.inf]), target)
    for correction in (0.0, math.nan):
        with pytest.raises(ValueError, match="tie correction"):
            rank_statistic_from_ranks(ranks, target, tie_correction=correction)
    with pytest.raises(ValueError, match="target and background"):
        rank_statistic_from_ranks(ranks, np.asarray([False, False], dtype=np.bool_))
    with pytest.raises(ValueError, match="target and background"):
        mann_whitney_rank_statistic(
            np.asarray([1.0], dtype=np.float64),
            np.asarray([True], dtype=np.bool_),
        )
    assert benjamini_hochberg(()) == ()


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("dimensions", "one-dimensional"),
        ("alignment", "aligned"),
        ("finite", "at least two finite"),
        ("axis", "axis indices are invalid"),
        ("replicates", "replicate count must be positive"),
        ("seed", "seed is outside"),
    ],
)
def test_permutation_input_guards(case: str, message: str) -> None:
    values = np.asarray([1.0, 2.0, 3.0, 4.0], dtype=np.float64)
    axes = np.asarray([0, 1, 2, 3], dtype=np.int64)
    ranks = np.asarray([1, 1, 1, 1], dtype=np.int64)
    replicates = 1
    seed = 1
    if case == "dimensions":
        values = values.reshape((2, 2))
    elif case == "alignment":
        axes = axes[:3]
    elif case == "finite":
        values[0] = math.nan
    elif case == "axis":
        axes[0] = 4
    elif case == "replicates":
        replicates = 0
    else:
        seed = -1
    with pytest.raises(ValueError, match=message):
        stratified_permutation_rank_test(
            values,
            axes,
            ranks,
            replicates=replicates,
            seed=seed,
        )


def test_single_permutation_has_zero_null_deviation_and_skips_singleton_strata() -> None:
    result = stratified_permutation_rank_test(
        np.asarray([4.0, 3.0, 2.0, 1.0], dtype=np.float64),
        np.asarray([0, 1, 2, 3], dtype=np.int64),
        np.asarray([1, 39, 77, 115], dtype=np.int64),
        replicates=1,
        seed=1,
    )
    assert result.replicates == 1
    assert result.null_standard_deviations == (0.0, 0.0, 0.0, 0.0)


@pytest.mark.parametrize(
    "updates",
    [
        {"huber_delta": 0.0},
        {"damping": 1.1},
        {"backtracking_factor": 1.0},
        {"max_iterations": 0},
        {"backtracking_steps": 0},
        {"objective_increase_tolerance": -1.0},
        {"objective_increase_tolerance": math.nan},
    ],
)
def test_solver_configuration_rejects_unsafe_numerical_constants(
    updates: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        _configuration(**updates)


def test_solver_parameter_and_objective_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    observations = (_solver_observation(),)
    configuration = _configuration()
    with pytest.raises(ValueError, match="parameter vector is invalid"):
        objective(np.zeros(4, dtype=np.float64), observations, configuration)
    with pytest.raises(ValueError, match="parameter vector is invalid"):
        objective(np.asarray([0.0, 0.0, 0.0, 0.0, math.nan]), observations, configuration)
    with pytest.raises(ValueError, match="initial parameter vector is invalid"):
        solve_constrained_latent(
            observations,
            configuration,
            initial=np.zeros(4, dtype=np.float64),
        )
    with pytest.raises(ValueError, match="initial parameter vector is invalid"):
        solve_constrained_latent(
            observations,
            configuration,
            initial=np.asarray([0.0, 0.0, 0.0, 0.0, math.inf]),
        )
    with monkeypatch.context() as patch:
        patch.setattr(solver_module, "_huber_loss", lambda _residual, _delta: math.inf)
        with pytest.raises(FloatingPointError, match="objective became non-finite"):
            objective(np.zeros(5, dtype=np.float64), observations, configuration)


def test_solver_linear_algebra_guards_reject_singular_or_nonfinite_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observations = (_solver_observation(),)
    configuration = _configuration()
    with monkeypatch.context() as patch:

        def singular(_matrix: object, _rhs: object) -> object:
            raise np.linalg.LinAlgError("singular")

        patch.setattr(np.linalg, "solve", singular)
        with pytest.raises(FloatingPointError, match="system is singular"):
            solver_module._irls_candidate(np.zeros(5), observations, configuration)
    with monkeypatch.context() as patch:
        patch.setattr(
            np.linalg,
            "solve",
            lambda _matrix, _rhs: np.full(6, math.nan, dtype=np.float64),
        )
        with pytest.raises(FloatingPointError, match="candidate became non-finite"):
            solver_module._irls_candidate(np.zeros(5), observations, configuration)


def test_solver_exhausts_backtracking_and_reports_nonconvergence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configuration = _configuration(max_iterations=1, backtracking_steps=3)
    observations = (_solver_observation(),)
    with monkeypatch.context() as patch:
        patch.setattr(
            solver_module,
            "_irls_candidate",
            lambda _current, _observations, _configuration: np.ones(5, dtype=np.float64),
        )
        patch.setattr(
            solver_module,
            "objective",
            lambda parameters, _observations, _configuration: (
                0.0 if np.all(parameters == 0.0) else 1.0
            ),
        )
        patch.setattr(
            solver_module,
            "_projected_gradient",
            lambda _parameters, _observations, _configuration: np.zeros(5),
        )
        outcome = solve_constrained_latent(observations, configuration)
    assert not outcome.converged
    assert outcome.iterations == 1
    assert outcome.objective_trace[0].accepted is False
    assert outcome.objective_trace[0].damping == 0.0


def test_binding_censor_contributes_only_above_its_upper_limit() -> None:
    configuration = _configuration()
    censored = (_solver_observation(value=-1.0, state="left_censored"),)
    binding = objective(np.zeros(5, dtype=np.float64), censored, configuration)
    nonbinding_parameters = np.asarray([-1.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float64)
    nonbinding = objective(nonbinding_parameters, censored, configuration)
    assert binding > nonbinding


def test_engine_partial_bootstrap_keeps_only_finite_converged_refits(
    analyzed_demo: tuple[FunctionalProteotypeRequest, FunctionalProteotypeResult],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, _result = analyzed_demo
    _declared, active = engine_module._mapped_observations(request)
    point = engine_module._solve(active, engine_module._solver_configuration())
    nonfinite = replace(_outcome(), axis_values=(math.nan, 0.2, -0.2, -0.6))
    outcomes: list[SolverOutcome | FloatingPointError] = [
        FloatingPointError("guard"),
        _outcome(converged=False),
        nonfinite,
        _outcome(),
    ]

    def next_outcome(*_args: object, **_kwargs: object) -> SolverOutcome:
        value = outcomes.pop(0)
        if isinstance(value, FloatingPointError):
            raise value
        return value

    with monkeypatch.context() as patch:
        patch.setattr(engine_module, "solve_constrained_latent", next_outcome)
        bootstrap = engine_module._bootstrap(
            active,
            engine_module._solver_configuration(),
            point,
            replicates=4,
            seed=11,
            cancellation=None,
        )
    assert bootstrap.shape == (1, 4)
    assert np.all(np.isfinite(bootstrap))

    with monkeypatch.context() as patch:
        patch.setattr(
            engine_module,
            "solve_constrained_latent",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(FloatingPointError("guard")),
        )
        empty = engine_module._bootstrap(
            active,
            engine_module._solver_configuration(),
            point,
            replicates=1,
            seed=11,
            cancellation=None,
        )
    assert empty.shape == (0, 4)


def test_rank_guard_interval_stability_and_discordance_helpers(
    analyzed_demo: tuple[FunctionalProteotypeRequest, FunctionalProteotypeResult],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, result = analyzed_demo
    declared, active = engine_module._mapped_observations(request)
    tied = tuple(
        replace(
            item,
            evidence=item.evidence.model_copy(update={"standardized_effect": 1.0}),
        )
        for item in active
    )
    assert engine_module._rank_comparisons(
        tied,
        replicates=64,
        seed=1,
        cancellation=None,
    ) == (None, None, None, None)
    with monkeypatch.context() as patch:
        patch.setattr(
            engine_module,
            "stratified_permutation_rank_test",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("invalid")),
        )
        assert engine_module._rank_comparisons(
            active,
            replicates=64,
            seed=1,
            cancellation=None,
        ) == (None, None, None, None)

    assert engine_module._effective_sample_size(()) == 0.0
    with monkeypatch.context() as patch:
        patch.setattr(engine_module, "_reliability", lambda _item: 0.0)
        assert engine_module._effective_sample_size(active[:2]) == 0.0
    assert engine_module._interval(0.0, np.zeros((15, 4)), 0) is None
    interval = engine_module._interval(0.5, np.zeros((16, 4)), 0)
    assert interval is not None
    assert interval.lower_bound == 0.0 and interval.upper_bound == 0.5
    assert engine_module._stability(0.5, np.empty((0, 4)), 0) == 0.0
    assert engine_module._discordance(0.5, None) == 0.0
    assert engine_module._discordance(0.5, result.axis_evidence[0].rank) >= 0.0
    assert len(declared) == len(request.observations)


def test_ablation_support_gates_and_refit_failures_are_explicit(
    analyzed_demo: tuple[FunctionalProteotypeRequest, FunctionalProteotypeResult],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, result = analyzed_demo
    _declared, active = engine_module._mapped_observations(request)
    axis_items = tuple(item for item in active if item.axis_index == 0)
    strong, reason = engine_module._coverage_gate(axis_items)
    assert strong and reason is None
    weak, reason = engine_module._coverage_gate(axis_items[:6])
    assert not weak
    assert reason is not None
    assert "active-protein coverage" in reason
    assert "observed-protein coverage" in reason
    assert "source-signature fraction" in reason

    configuration = engine_module._solver_configuration()
    baseline = cast("LatentInterval", result.axis_evidence[0].latent).estimate
    with pytest.raises(AssertionError, match="must remove active"):
        engine_module._one_ablation(
            axis_index=0,
            kind=AblationKind.TOP_DRIVER,
            target="none",
            removed_symbols=frozenset(("NOT_PRESENT",)),
            baseline_estimate=baseline,
            active=active,
            configuration=configuration,
            cancellation=None,
        )

    remove_twenty = frozenset(item.protein.gene_symbol for item in axis_items[:20])
    too_small = engine_module._one_ablation(
        axis_index=0,
        kind=AblationKind.SOURCE_RANK_QUARTILE,
        target="large-removal",
        removed_symbols=remove_twenty,
        baseline_estimate=baseline,
        active=active,
        configuration=configuration,
        cancellation=None,
    )
    assert too_small.support_after_ablation is AnalysisSupport.ABSTAINED

    remove_one = frozenset((axis_items[0].protein.gene_symbol,))
    with monkeypatch.context() as patch:
        patch.setattr(
            engine_module,
            "_solve",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(FloatingPointError("guard")),
        )
        guarded = engine_module._one_ablation(
            axis_index=0,
            kind=AblationKind.TOP_DRIVER,
            target="guarded",
            removed_symbols=remove_one,
            baseline_estimate=baseline,
            active=active,
            configuration=configuration,
            cancellation=None,
        )
    assert guarded.support_after_ablation is AnalysisSupport.ABSTAINED
    assert "did not converge" in cast("str", guarded.reason)

    with monkeypatch.context() as patch:
        patch.setattr(engine_module, "_solve", lambda *_args, **_kwargs: _outcome(converged=False))
        nonconverged = engine_module._one_ablation(
            axis_index=0,
            kind=AblationKind.TOP_DRIVER,
            target="nonconverged",
            removed_symbols=remove_one,
            baseline_estimate=baseline,
            active=active,
            configuration=configuration,
            cancellation=None,
        )
    assert nonconverged.support_after_ablation is AnalysisSupport.ABSTAINED

    remove_eleven = frozenset(item.protein.gene_symbol for item in axis_items[:11])
    with monkeypatch.context() as patch:
        patch.setattr(engine_module, "_solve", lambda *_args, **_kwargs: _outcome())
        limited = engine_module._one_ablation(
            axis_index=0,
            kind=AblationKind.EVIDENCE_STATE,
            target="limited",
            removed_symbols=remove_eleven,
            baseline_estimate=baseline,
            active=active,
            configuration=configuration,
            cancellation=None,
        )
        supported = engine_module._one_ablation(
            axis_index=0,
            kind=AblationKind.TOP_DRIVER,
            target="supported",
            removed_symbols=remove_one,
            baseline_estimate=baseline,
            active=active,
            configuration=configuration,
            cancellation=None,
        )
    assert limited.support_after_ablation is AnalysisSupport.LIMITED
    assert limited.reason is not None
    assert supported.support_after_ablation is AnalysisSupport.SUPPORTED
    assert supported.reason is None


def test_support_reasons_distinguish_abstained_limited_and_supported() -> None:
    interval = LatentInterval(
        estimate=0.6,
        lower_bound=0.4,
        upper_bound=0.8,
        bootstrap_replicates_used=16,
    )
    support, reasons = engine_module._support_reasons(
        counts=_counts(observed=5),
        effective_sample_size=5.0,
        rank=None,
        interval=interval,
        bootstrap_successes=16,
        requested_bootstraps=16,
    )
    assert support is AnalysisSupport.ABSTAINED
    assert "exploratory" in reasons[0]

    support, reasons = engine_module._support_reasons(
        counts=_counts(observed=6),
        effective_sample_size=6.0,
        rank=None,
        interval=None,
        bootstrap_successes=0,
        requested_bootstraps=16,
    )
    assert support is AnalysisSupport.ABSTAINED
    assert "bootstrap" in reasons[0]

    support, reasons = engine_module._support_reasons(
        counts=_counts(observed=6),
        effective_sample_size=2.0,
        rank=None,
        interval=interval,
        bootstrap_successes=8,
        requested_bootstraps=16,
    )
    assert support is AnalysisSupport.LIMITED
    assert len(reasons) >= 6

    support, reasons = engine_module._support_reasons(
        counts=_counts(),
        effective_sample_size=15.0,
        rank=_rank(q_value=0.2, rank_biserial=-0.5),
        interval=interval,
        bootstrap_successes=16,
        requested_bootstraps=16,
    )
    assert support is AnalysisSupport.LIMITED
    assert any("q-value" in reason for reason in reasons)
    assert any("opposing" in reason for reason in reasons)

    support, reasons = engine_module._support_reasons(
        counts=_counts(),
        effective_sample_size=15.0,
        rank=_rank(),
        interval=interval,
        bootstrap_successes=16,
        requested_bootstraps=16,
    )
    assert support is AnalysisSupport.SUPPORTED
    assert reasons == ()


def test_engine_analysis_fails_safe_on_numerical_guard_nonconvergence_and_partial_bootstrap(
    analyzed_demo: tuple[FunctionalProteotypeRequest, FunctionalProteotypeResult],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, _result = analyzed_demo
    one_observation = request.model_copy(update={"observations": request.observations[:1]})
    with monkeypatch.context() as patch:
        patch.setattr(
            engine_module,
            "_solve",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(FloatingPointError("guard")),
        )
        guarded = engine_module.analyze_functional_proteotype(one_observation)
    assert guarded.solver.termination is SolverTermination.NUMERICAL_GUARD
    assert all(item.support is AnalysisSupport.ABSTAINED for item in guarded.axis_evidence)

    with monkeypatch.context() as patch:
        patch.setattr(engine_module, "_solve", lambda *_args, **_kwargs: _outcome(converged=False))
        nonconverged = engine_module.analyze_functional_proteotype(one_observation)
    assert nonconverged.solver.termination is SolverTermination.MAXIMUM_ITERATIONS
    assert all(item.latent is None for item in nonconverged.axis_evidence)

    with monkeypatch.context() as patch:
        patch.setattr(engine_module, "_bootstrap", lambda *_args, **_kwargs: np.zeros((15, 4)))
        partial = engine_module.analyze_functional_proteotype(request)
    assert partial.provenance.bootstrap_replicates_used == 15
    assert all(item.support is AnalysisSupport.ABSTAINED for item in partial.axis_evidence)
    assert all(
        any("bootstrap" in reason.lower() for reason in item.abstention_reasons)
        for item in partial.axis_evidence
    )


def test_profile_engine_source_and_numpy_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(RuntimeError, match=r"source\.article_title is invalid"):
        profile_module._source_text({"article_title": ""}, "article_title")
    with pytest.raises(RuntimeError, match=r"source\.article_title is invalid"):
        engine_module._source_text({"article_title": 1}, "article_title")

    with monkeypatch.context() as patch:
        patch.setattr(np, "__version__", "0.0.0")
        with pytest.raises(RuntimeError, match=r"requires NumPy 2\.5\.2"):
            profile_module.algorithm_profile()

    catalog = catalog_module.functional_proteotype_catalog()
    forged_source = {**catalog.source, "source_sha256": DIGEST_A}
    forged_catalog = replace(catalog, source=forged_source)
    with monkeypatch.context() as patch:
        patch.setattr(profile_module, "functional_proteotype_catalog", lambda: forged_catalog)
        with pytest.raises(RuntimeError, match="workbook is not pinned"):
            profile_module.algorithm_profile()


def test_every_behavior_defining_source_file_changes_the_engine_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = {
        "canonical.py",
        "catalog.py",
        "contracts.py",
        "engine.py",
        "profile.py",
        "solver.py",
        "statistics.py",
    }
    assert set(profile_module._COMPUTATIONAL_SOURCE_FILES) == expected

    class Resource:
        def __init__(self, content: bytes) -> None:
            self.content = content

        def read_bytes(self) -> bytes:
            return self.content

    class Root:
        def __init__(self, contents: dict[str, bytes]) -> None:
            self.contents = contents

        def joinpath(self, name: str) -> Resource:
            return Resource(self.contents[name])

    contents = {name: f"semantic:{name}\n".encode() for name in expected}
    monkeypatch.setattr(profile_module, "files", lambda _package: Root(contents))
    baseline = profile_module.computational_source_digest()
    for name in expected:
        mutated = {**contents, name: contents[name] + b"behavior-change\n"}
        monkeypatch.setattr(profile_module, "files", lambda _package, rows=mutated: Root(rows))
        assert profile_module.computational_source_digest() != baseline


def test_service_methods_and_alias_preserve_exact_stateless_results(
    analyzed_demo: tuple[FunctionalProteotypeRequest, FunctionalProteotypeResult],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, result = analyzed_demo
    verification = ReplayVerificationRequest(request=request, result=result)
    verified = service_module.verify_replay(verification)
    service = FunctionalProteotypeService()
    with monkeypatch.context() as patch:
        patch.setattr(
            service_module,
            "analyze_functional_proteotype",
            lambda *_args, **_kwargs: result,
        )
        patch.setattr(service_module, "verify_replay", lambda *_args, **_kwargs: verified)
        assert service.analyze(request) is result
        assert service.verify(verification) is verified
        assert service_module.verify_functional_proteotype_replay(verification) is verified
