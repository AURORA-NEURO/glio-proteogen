"""Content-bound numerical profile for KNCC/Neftel program transitions."""

from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from importlib.resources import files
from typing import Final, cast

import numpy as np
from pydantic import TypeAdapter

from .canonical import profile_payload_digest, sha256_digest
from .contracts import (
    REQUIRED_ASSAY_COMPATIBILITY,
    LongitudinalGbmNeftelTransitionProfile,
    LongitudinalGbmNeftelTransitionRequest,
    NeftelProgramAlgorithmConstants,
    NeftelProgramEvaluationSummary,
    NeftelProgramLimits,
    NeftelProgramProfile,
    NeftelProgramSourceModelCounts,
    NeftelProgramSourceModelDigests,
)
from .demo import DEMO_ID, EXPECTED_DEMO_SEMANTIC_ORACLE_DIGEST, demo_request_digest
from .errors import NeftelConditionalModelIntegrityError
from .fitted_catalog import neftel_program_fitted_catalog

EXPECTED_NUMPY_VERSION: Final = "2.5.2"
_SEMANTIC_SOURCE_FILES: Final = (
    "canonical.py",
    "catalog.py",
    "contracts.py",
    "fitted_catalog.py",
    "solver.py",
    "engine.py",
)

CONSTANTS = NeftelProgramAlgorithmConstants()
LIMITS = NeftelProgramLimits()


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise NeftelConditionalModelIntegrityError(
            f"fitted Neftel evaluation field {name!r} is not an object"
        )
    return cast("Mapping[str, object]", value)


def _sequence(value: object, name: str) -> Sequence[object]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise NeftelConditionalModelIntegrityError(
            f"fitted Neftel evaluation field {name!r} is not an array"
        )
    return cast("Sequence[object]", value)


def _integer(value: object, name: str) -> int:
    if type(value) is not int:
        raise RuntimeError(f"fitted Neftel evaluation field {name!r} is not an integer")
    return value


def _number(value: object, name: str) -> float:
    if type(value) not in {int, float}:
        raise RuntimeError(f"fitted Neftel evaluation field {name!r} is not numeric")
    return float(cast("int | float", value))


def _canonical_python_ast(source: bytes) -> str:
    text = source.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return ast.dump(
        ast.parse(text),
        annotate_fields=True,
        include_attributes=False,
    )


def engine_semantic_digest() -> str:
    """Bind the location-free ASTs that define numerical semantics."""

    root = files(__package__)
    return sha256_digest(
        {
            name: _canonical_python_ast(root.joinpath(name).read_bytes())
            for name in _SEMANTIC_SOURCE_FILES
        }
    )


def input_contract_schema_digest() -> str:
    """Bind the exact strict request schema reused by every transport."""

    return sha256_digest(TypeAdapter(LongitudinalGbmNeftelTransitionRequest).json_schema())


def _program_profiles() -> tuple[NeftelProgramProfile, ...]:
    fitted = neftel_program_fitted_catalog()
    source = fitted.source_catalog
    result: list[NeftelProgramProfile] = []
    for fitted_program, source_program in zip(fitted.programs, source.programs, strict=True):
        result.append(
            NeftelProgramProfile(
                program_index=fitted_program.program_index,
                domain_id=fitted_program.domain_id,
                program_id=fitted_program.program_id,
                program_name=fitted_program.name,
                source_member_count=source_program.source_member_count,
                mapped_feature_count=source_program.mapped_feature_count,
                eligible_feature_count=source_program.eligible_feature_count,
                fitted_feature_count=sum(
                    bool(fitted.reference_eligible[position])
                    for position in fitted_program.member_local_indices
                ),
                unique_fitted_feature_count=sum(
                    bool(fitted.reference_eligible[position])
                    for position in fitted_program.unique_member_local_indices
                ),
                overlap_confounded=not fitted_program.unique_member_local_indices,
            )
        )
    return tuple(result)


def _source_terms() -> tuple[str, ...]:
    source = neftel_program_fitted_catalog().source_catalog
    return (
        f"PDC000514 source: {source.provenance['kncc_source_license']}",
        "Neftel Table S2 terms/license state is not asserted by this derived catalog.",
    )


def _source_attribution() -> str:
    source = neftel_program_fitted_catalog().source_catalog
    return (
        f"{source.provenance['kncc_attribution']}; Neftel et al. Table S2, "
        f"DOI {source.neftel_article_doi}, source digest {source.neftel_table_s2_sha256}."
    )


def _source_model_counts() -> NeftelProgramSourceModelCounts:
    fitted = neftel_program_fitted_catalog()
    return NeftelProgramSourceModelCounts(
        fitted_global_feature_count=int(np.count_nonzero(fitted.reference_eligible)),
        fitted_program_feature_count=sum(
            bool(fitted.reference_eligible[position])
            for program in fitted.programs
            for position in program.member_local_indices
        ),
        outer_fold_count=8,
        marker_fold_count=5,
    )


def _source_model_digests() -> NeftelProgramSourceModelDigests:
    fitted = neftel_program_fitted_catalog()
    source = fitted.source_catalog
    return NeftelProgramSourceModelDigests(
        source_catalog_artifact_digest=source.artifact_byte_digest,
        source_catalog_content_digest=source.content_digest,
        source_binding_digest=source.source_binding_digest,
        neftel_source_program_digest=source.neftel_source_program_digest,
        program_order_digest=source.program_order_digest,
        program_membership_digest=source.program_membership_digest,
        gene_order_digest=source.gene_order_digest,
        patient_order_rule_digest=source.patient_order_rule_digest,
        fitted_artifact_digest=fitted.artifact_byte_digest,
        fitted_content_digest=fitted.content_digest,
        fitted_source_catalog_binding_digest=fitted.source_catalog_binding_digest,
        union_feature_digest=fitted.union_feature_digest,
        program_inventory_digest=fitted.program_inventory_digest,
        membership_degree_digest=fitted.membership_degree_digest,
        reference_tensor_digest=fitted.reference_tensor_digest,
        centering_scaling_digest=fitted.centering_scaling_digest,
        reference_design_digest=fitted.reference_design_digest,
        equal_membership_design_digest=fitted.equal_membership_design_digest,
        global_loading_digest=fitted.global_loading_digest,
        conditional_loading_digest=fitted.conditional_loading_digest,
        bootstrap_seed_namespace_digest=fitted.bootstrap_seed_namespace_digest,
        bootstrap_ensemble_digest=fitted.bootstrap_ensemble_digest,
        training_recipe_digest=fitted.training_recipe_digest,
        fold_policy_digest=fitted.fold_policy_digest,
        source_processing_ablation_digest=fitted.source_processing_ablation_digest,
        evaluation_digest=fitted.evaluation_digest,
        input_contract_schema_digest=input_contract_schema_digest(),
        engine_semantic_digest=engine_semantic_digest(),
    )


def _evaluation_summary() -> NeftelProgramEvaluationSummary:
    evaluation = neftel_program_fitted_catalog().evaluation
    roles = _mapping(
        evaluation.get("solver_nonconverged_by_role"),
        "solver_nonconverged_by_role",
    )
    global_interval = _sequence(
        evaluation.get("patient_cluster_joint_vs_global_median_gain_90_interval"),
        "patient_cluster_joint_vs_global_median_gain_90_interval",
    )
    equal_interval = _sequence(
        evaluation.get("patient_cluster_joint_vs_equal_median_gain_90_interval"),
        "patient_cluster_joint_vs_equal_median_gain_90_interval",
    )
    if len(global_interval) != 2 or len(equal_interval) != 2:
        raise RuntimeError("fitted Neftel patient-cluster intervals must have two bounds")
    cosine_minima = _sequence(
        evaluation.get("outer_loading_cosine_minima"),
        "outer_loading_cosine_minima",
    )
    if len(cosine_minima) != 9:
        raise RuntimeError("fitted Neftel loading cosine inventory must have nine entries")
    leave_program = _sequence(
        evaluation.get("leave_program_out"),
        "leave_program_out",
    )
    interval_crosses_zero: list[bool] = []
    for index, raw_item in enumerate(leave_program):
        item = _mapping(raw_item, f"leave_program_out[{index}]")
        interval_crosses_zero.append(
            _number(item.get("q05"), f"leave_program_out[{index}].q05")
            <= 0.0
            <= _number(item.get("q95"), f"leave_program_out[{index}].q95")
        )
    return NeftelProgramEvaluationSummary.model_validate(
        {
            "protocol": evaluation.get("protocol"),
            "validation_scope": evaluation.get("validation_scope"),
            "interpretation": evaluation.get("interpretation"),
            "release_gate": evaluation.get("release_gate"),
            "patient_count": _integer(evaluation.get("patient_count"), "patient_count"),
            "evaluation_count": _integer(evaluation.get("evaluation_count"), "evaluation_count"),
            "union_feature_count": _integer(
                evaluation.get("union_feature_count"), "union_feature_count"
            ),
            "zero_prediction_median_standardized_mae": _number(
                evaluation.get("zero_prediction_median_standardized_mae"),
                "zero_prediction_median_standardized_mae",
            ),
            "global_only_median_standardized_mae": _number(
                evaluation.get("global_only_median_standardized_mae"),
                "global_only_median_standardized_mae",
            ),
            "equal_membership_median_standardized_mae": _number(
                evaluation.get("equal_membership_median_standardized_mae"),
                "equal_membership_median_standardized_mae",
            ),
            "joint_median_standardized_mae": _number(
                evaluation.get("joint_median_standardized_mae"),
                "joint_median_standardized_mae",
            ),
            "joint_vs_global_median_relative_mae_gain": _number(
                evaluation.get("joint_vs_global_median_relative_mae_gain"),
                "joint_vs_global_median_relative_mae_gain",
            ),
            "joint_vs_equal_median_relative_mae_gain": _number(
                evaluation.get("joint_vs_equal_median_relative_mae_gain"),
                "joint_vs_equal_median_relative_mae_gain",
            ),
            "joint_vs_global_evaluation_improved_fraction": _number(
                evaluation.get("joint_vs_global_evaluation_improved_fraction"),
                "joint_vs_global_evaluation_improved_fraction",
            ),
            "joint_vs_equal_evaluation_improved_fraction": _number(
                evaluation.get("joint_vs_equal_evaluation_improved_fraction"),
                "joint_vs_equal_evaluation_improved_fraction",
            ),
            "patient_cluster_joint_vs_global_median_gain": _number(
                evaluation.get("patient_cluster_joint_vs_global_median_gain"),
                "patient_cluster_joint_vs_global_median_gain",
            ),
            "patient_cluster_joint_vs_equal_median_gain": _number(
                evaluation.get("patient_cluster_joint_vs_equal_median_gain"),
                "patient_cluster_joint_vs_equal_median_gain",
            ),
            "patient_cluster_joint_vs_global_median_gain_90_interval": (
                _number(global_interval[0], "joint_vs_global_interval.lower"),
                _number(global_interval[1], "joint_vs_global_interval.upper"),
            ),
            "patient_cluster_joint_vs_equal_median_gain_90_interval": (
                _number(equal_interval[0], "joint_vs_equal_interval.lower"),
                _number(equal_interval[1], "joint_vs_equal_interval.upper"),
            ),
            "joint_vs_global_patient_cluster_interval_supports_positive_gain": evaluation.get(
                "joint_vs_global_patient_cluster_interval_supports_positive_gain"
            ),
            "joint_vs_equal_patient_cluster_interval_supports_positive_gain": evaluation.get(
                "joint_vs_equal_patient_cluster_interval_supports_positive_gain"
            ),
            "patient_cluster_bootstrap_replicates": _integer(
                evaluation.get("patient_cluster_bootstrap_replicates"),
                "patient_cluster_bootstrap_replicates",
            ),
            "reference_design_condition_number": _number(
                evaluation.get("reference_design_condition_number"),
                "reference_design_condition_number",
            ),
            "equal_membership_reference_design_condition_number": _number(
                evaluation.get("equal_membership_reference_design_condition_number"),
                "equal_membership_reference_design_condition_number",
            ),
            "outer_design_condition_minimum": _number(
                evaluation.get("outer_design_condition_minimum"),
                "outer_design_condition_minimum",
            ),
            "outer_design_condition_maximum": _number(
                evaluation.get("outer_design_condition_maximum"),
                "outer_design_condition_maximum",
            ),
            "outer_equal_membership_condition_minimum": _number(
                evaluation.get("outer_equal_membership_condition_minimum"),
                "outer_equal_membership_condition_minimum",
            ),
            "outer_equal_membership_condition_maximum": _number(
                evaluation.get("outer_equal_membership_condition_maximum"),
                "outer_equal_membership_condition_maximum",
            ),
            "minimum_outer_loading_cosine": min(
                _number(value, "outer_loading_cosine_minima") for value in cosine_minima
            ),
            "full_patient_nonconverged_count": _integer(
                roles.get("full_patient"),
                "solver_nonconverged_by_role.full_patient",
            ),
            "global_held_marker_nonconverged_count": _integer(
                roles.get("global_held_marker"),
                "solver_nonconverged_by_role.global_held_marker",
            ),
            "equal_membership_held_marker_nonconverged_count": _integer(
                roles.get("equal_membership_held_marker"),
                "solver_nonconverged_by_role.equal_membership_held_marker",
            ),
            "joint_held_marker_nonconverged_count": _integer(
                roles.get("joint_held_marker"),
                "solver_nonconverged_by_role.joint_held_marker",
            ),
            "leave_program_out_nonconverged_count": _integer(
                roles.get("leave_program_out"),
                "solver_nonconverged_by_role.leave_program_out",
            ),
            "all_primary_solver_fits_converged": True,
            "individually_supported_program_count": len(
                _sequence(
                    evaluation.get("individually_supported_program_ids"),
                    "individually_supported_program_ids",
                )
            ),
            "leave_program_interval_count": len(leave_program),
            "all_leave_program_q05_q95_intervals_cross_zero": all(interval_crosses_zero),
        },
        strict=True,
    )


def algorithm_profile() -> LongitudinalGbmNeftelTransitionProfile:
    """Return the immutable profile only after both source artifacts validate."""

    if np.__version__ != EXPECTED_NUMPY_VERSION:
        raise RuntimeError("Neftel conditional transition requires NumPy 2.5.2")
    fitted = neftel_program_fitted_catalog()
    if fitted.numpy_version != EXPECTED_NUMPY_VERSION:
        raise RuntimeError("fitted Neftel artifact NumPy version is incompatible")
    if fitted.profile_id != "kncc-neftel-program-transition/1.0.0":
        raise RuntimeError("fitted Neftel artifact profile identifier is incompatible")
    if fitted.model_id != "kncc-neftel-program-transition-model/1.0.0":
        raise RuntimeError("fitted Neftel artifact model identifier is incompatible")
    programs = _program_profiles()
    counts = _source_model_counts()
    digests = _source_model_digests()
    evaluation = _evaluation_summary()
    source_terms = _source_terms()
    attribution = _source_attribution()
    transformation_notice = (
        f"{fitted.source_catalog.provenance['kncc_transformation_notice']} "
        "Neftel markers were normalized through the pinned HGNC catalog and projected "
        "onto the frozen KNCC protein axis."
    )
    payload = {
        "algorithm_id": "kncc-neftel-program-transition",
        "algorithm_version": "1.0.0",
        "profile_id": "kncc-neftel-program-transition/1.0.0",
        "model_id": "kncc-neftel-program-transition-model/1.0.0",
        "parent_feature_axis_model_id": "kncc-paired-protein-transition/1.0.0",
        "parent_dependency_semantics": (
            "feature_axis_and_assay_binding_only_no_runtime_delegation"
        ),
        "required_assay_compatibility": REQUIRED_ASSAY_COMPATIBILITY.model_dump(mode="json"),
        "constants": CONSTANTS.model_dump(mode="json"),
        "limits": LIMITS.model_dump(mode="json"),
        "counts": counts.model_dump(mode="json"),
        "digests": digests.model_dump(mode="json"),
        "evaluation": evaluation.model_dump(mode="json"),
        "programs": [program.model_dump(mode="json") for program in programs],
        "numpy_version": np.__version__,
        "demo_id": DEMO_ID,
        "demo_request_digest": demo_request_digest(),
        "demo_semantic_oracle_digest": EXPECTED_DEMO_SEMANTIC_ORACLE_DIGEST,
        "source_attribution": attribution,
        "source_terms": source_terms,
        "source_transformation_notice": transformation_notice,
        "safety_class": "research_use_only",
        "claim_ceiling": ("paired_source_cohort_bulk_protein_program_transition_concordance_only"),
        "interpretation": (
            "global_adjusted_neftel_program_coordinate_not_recurrence_prediction_evolution_"
            "subtype_deconvolution_or_activation"
        ),
        "maximum_evidence_grade": "limited_same_cohort_without_external_validation",
    }
    return LongitudinalGbmNeftelTransitionProfile(
        required_assay_compatibility=REQUIRED_ASSAY_COMPATIBILITY,
        constants=CONSTANTS,
        limits=LIMITS,
        counts=counts,
        digests=digests,
        evaluation=evaluation,
        programs=programs,
        numpy_version=np.__version__,
        demo_id=DEMO_ID,
        demo_request_digest=demo_request_digest(),
        demo_semantic_oracle_digest=EXPECTED_DEMO_SEMANTIC_ORACLE_DIGEST,
        source_attribution=attribution,
        source_terms=source_terms,
        source_transformation_notice=transformation_notice,
        profile_digest=profile_payload_digest(payload),
    )


__all__ = [
    "CONSTANTS",
    "EXPECTED_NUMPY_VERSION",
    "LIMITS",
    "algorithm_profile",
    "engine_semantic_digest",
    "input_contract_schema_digest",
]
