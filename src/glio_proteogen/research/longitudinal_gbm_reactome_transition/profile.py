"""Content-bound numerical profile for Reactome conditional-transition concordance."""

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
    LongitudinalGbmReactomeTransitionProfile,
    LongitudinalGbmReactomeTransitionRequest,
    ReactomeConditionalAlgorithmConstants,
    ReactomeConditionalEvaluationSummary,
    ReactomeConditionalLimits,
    ReactomeConditionalSourceModelCounts,
    ReactomeConditionalSourceModelDigests,
    ReactomePathwayProfile,
)
from .demo import DEMO_ID, EXPECTED_DEMO_SEMANTIC_ORACLE_DIGEST, demo_request_digest
from .errors import ReactomeConditionalModelIntegrityError
from .fitted_catalog import reactome_conditional_fitted_catalog

EXPECTED_NUMPY_VERSION: Final = "2.5.2"
_SEMANTIC_SOURCE_FILES: Final = (
    "canonical.py",
    "catalog.py",
    "contracts.py",
    "fitted_catalog.py",
    "solver.py",
    "engine.py",
)

CONSTANTS = ReactomeConditionalAlgorithmConstants()
LIMITS = ReactomeConditionalLimits()


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ReactomeConditionalModelIntegrityError(
            f"fitted Reactome evaluation field {name!r} is not an object"
        )
    return cast("Mapping[str, object]", value)


def _sequence(value: object, name: str) -> Sequence[object]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ReactomeConditionalModelIntegrityError(
            f"fitted Reactome evaluation field {name!r} is not an array"
        )
    return cast("Sequence[object]", value)


def _integer(value: object, name: str) -> int:
    if type(value) is not int:
        raise RuntimeError(f"fitted Reactome evaluation field {name!r} is not an integer")
    return value


def _number(value: object, name: str) -> float:
    if type(value) not in {int, float}:
        raise RuntimeError(f"fitted Reactome evaluation field {name!r} is not numeric")
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

    return sha256_digest(TypeAdapter(LongitudinalGbmReactomeTransitionRequest).json_schema())


def _pathway_profiles() -> tuple[ReactomePathwayProfile, ...]:
    fitted = reactome_conditional_fitted_catalog()
    source = fitted.source_catalog
    result: list[ReactomePathwayProfile] = []
    for fitted_pathway, source_pathway in zip(fitted.pathways, source.pathways, strict=True):
        result.append(
            ReactomePathwayProfile(
                panel_index=fitted_pathway.panel_index,
                domain_id=fitted_pathway.domain_id,
                reactome_id=fitted_pathway.reactome_id,
                pathway_name=fitted_pathway.name,
                source_member_count=source_pathway.source_member_count,
                mapped_feature_count=source_pathway.mapped_feature_count,
                eligible_feature_count=source_pathway.eligible_feature_count,
                fitted_feature_count=sum(
                    bool(fitted.reference_eligible[position])
                    for position in fitted_pathway.member_local_indices
                ),
                unique_fitted_feature_count=sum(
                    bool(fitted.reference_eligible[position])
                    for position in fitted_pathway.unique_member_local_indices
                ),
                overlap_confounded=fitted_pathway.reactome_id == "R-HSA-198203",
            )
        )
    return tuple(result)


def _source_licenses() -> tuple[str, ...]:
    source = reactome_conditional_fitted_catalog().source_catalog
    return (
        f"PDC000514 article/data: {source.provenance['pdc_license']}",
        f"Reactome annotation: {source.provenance['reactome_annotation_license']}",
    )


def _source_attribution() -> str:
    source = reactome_conditional_fitted_catalog().source_catalog
    return (
        f"{source.provenance['pdc_article']}; "
        f"{source.provenance['reactome_resource']} release {source.reactome_release}."
    )


def _source_model_counts() -> ReactomeConditionalSourceModelCounts:
    fitted = reactome_conditional_fitted_catalog()
    return ReactomeConditionalSourceModelCounts(
        fitted_global_feature_count=int(np.count_nonzero(fitted.reference_eligible)),
        fitted_pathway_feature_count=sum(
            bool(fitted.reference_eligible[position])
            for pathway in fitted.pathways
            for position in pathway.member_local_indices
        ),
        outer_fold_count=8,
        gene_fold_count=5,
    )


def _source_model_digests() -> ReactomeConditionalSourceModelDigests:
    fitted = reactome_conditional_fitted_catalog()
    source = fitted.source_catalog
    return ReactomeConditionalSourceModelDigests(
        source_catalog_artifact_digest=source.artifact_byte_digest,
        source_catalog_content_digest=source.content_digest,
        source_binding_digest=source.source_binding_digest,
        selection_candidate_digest=source.selection_candidate_digest,
        pathway_order_digest=source.pathway_order_digest,
        pathway_membership_digest=source.pathway_membership_digest,
        gene_order_digest=source.gene_order_digest,
        patient_order_rule_digest=source.patient_order_rule_digest,
        fitted_artifact_digest=fitted.artifact_byte_digest,
        fitted_content_digest=fitted.content_digest,
        union_feature_digest=fitted.union_feature_digest,
        reference_tensor_digest=fitted.reference_tensor_digest,
        centering_scaling_digest=fitted.centering_scaling_digest,
        reference_design_digest=fitted.reference_design_digest,
        global_loading_digest=fitted.global_loading_digest,
        conditional_loading_digest=fitted.conditional_loading_digest,
        bootstrap_ensemble_digest=fitted.bootstrap_ensemble_digest,
        training_recipe_digest=fitted.training_recipe_digest,
        fold_policy_digest=fitted.fold_policy_digest,
        source_processing_ablation_digest=fitted.source_processing_ablation_digest,
        evaluation_digest=fitted.evaluation_digest,
        input_contract_schema_digest=input_contract_schema_digest(),
        engine_semantic_digest=engine_semantic_digest(),
    )


def _evaluation_summary() -> ReactomeConditionalEvaluationSummary:
    evaluation = reactome_conditional_fitted_catalog().evaluation
    roles = _mapping(
        evaluation.get("solver_nonconverged_by_role"),
        "solver_nonconverged_by_role",
    )
    cluster_interval = _sequence(
        evaluation.get("patient_cluster_median_improvement_90_interval"),
        "patient_cluster_median_improvement_90_interval",
    )
    if len(cluster_interval) != 2:
        raise RuntimeError("fitted Reactome patient-cluster interval must have two bounds")
    cosine_minima = _sequence(
        evaluation.get("outer_loading_cosine_minima"),
        "outer_loading_cosine_minima",
    )
    if len(cosine_minima) != 11:
        raise RuntimeError("fitted Reactome loading cosine inventory must have 11 entries")
    leave_pathway = _sequence(
        evaluation.get("leave_pathway_out"),
        "leave_pathway_out",
    )
    interval_crosses_zero: list[bool] = []
    for index, raw_item in enumerate(leave_pathway):
        item = _mapping(raw_item, f"leave_pathway_out[{index}]")
        interval_crosses_zero.append(
            _number(item.get("q05"), f"leave_pathway_out[{index}].q05")
            <= 0.0
            <= _number(item.get("q95"), f"leave_pathway_out[{index}].q95")
        )
    return ReactomeConditionalEvaluationSummary.model_validate(
        {
            "protocol": evaluation.get("protocol"),
            "validation_scope": evaluation.get("validation_scope"),
            "interpretation": evaluation.get("interpretation"),
            "patient_count": _integer(evaluation.get("patient_count"), "patient_count"),
            "evaluation_count": _integer(
                evaluation.get("evaluation_count"), "evaluation_count"
            ),
            "zero_prediction_median_standardized_mae": _number(
                evaluation.get("zero_prediction_median_standardized_mae"),
                "zero_prediction_median_standardized_mae",
            ),
            "global_only_median_standardized_mae": _number(
                evaluation.get("global_only_median_standardized_mae"),
                "global_only_median_standardized_mae",
            ),
            "joint_median_standardized_mae": _number(
                evaluation.get("joint_median_standardized_mae"),
                "joint_median_standardized_mae",
            ),
            "median_relative_mae_improvement": _number(
                evaluation.get("median_relative_mae_improvement"),
                "median_relative_mae_improvement",
            ),
            "evaluation_improved_fraction": _number(
                evaluation.get("evaluation_improved_fraction"),
                "evaluation_improved_fraction",
            ),
            "patient_cluster_median_improvement": _number(
                evaluation.get("patient_cluster_median_improvement"),
                "patient_cluster_median_improvement",
            ),
            "patient_cluster_median_improvement_90_interval": (
                _number(cluster_interval[0], "patient_cluster_interval.lower"),
                _number(cluster_interval[1], "patient_cluster_interval.upper"),
            ),
            "patient_cluster_bootstrap_replicates": _integer(
                evaluation.get("patient_cluster_bootstrap_replicates"),
                "patient_cluster_bootstrap_replicates",
            ),
            "reference_design_condition_number": _number(
                evaluation.get("reference_design_condition_number"),
                "reference_design_condition_number",
            ),
            "outer_design_condition_minimum": _number(
                evaluation.get("outer_design_condition_minimum"),
                "outer_design_condition_minimum",
            ),
            "outer_design_condition_maximum": _number(
                evaluation.get("outer_design_condition_maximum"),
                "outer_design_condition_maximum",
            ),
            "minimum_outer_loading_cosine": min(
                _number(value, "outer_loading_cosine_minima")
                for value in cosine_minima
            ),
            "full_patient_nonconverged_count": _integer(
                roles.get("full_patient"),
                "solver_nonconverged_by_role.full_patient",
            ),
            "global_held_gene_nonconverged_count": _integer(
                roles.get("global_held_gene"),
                "solver_nonconverged_by_role.global_held_gene",
            ),
            "joint_held_gene_nonconverged_count": _integer(
                roles.get("joint_held_gene"),
                "solver_nonconverged_by_role.joint_held_gene",
            ),
            "leave_pathway_out_nonconverged_count": _integer(
                roles.get("leave_pathway_out"),
                "solver_nonconverged_by_role.leave_pathway_out",
            ),
            "all_primary_solver_fits_converged": True,
            "leave_pathway_interval_count": len(leave_pathway),
            "all_leave_pathway_q05_q95_intervals_cross_zero": all(
                interval_crosses_zero
            ),
        },
        strict=True,
    )


def algorithm_profile() -> LongitudinalGbmReactomeTransitionProfile:
    """Return the immutable profile only after both source artifacts validate."""

    if np.__version__ != EXPECTED_NUMPY_VERSION:
        raise RuntimeError("Reactome conditional transition requires NumPy 2.5.2")
    fitted = reactome_conditional_fitted_catalog()
    if fitted.numpy_version != EXPECTED_NUMPY_VERSION:
        raise RuntimeError("fitted Reactome artifact NumPy version is incompatible")
    if fitted.profile_id != "kncc-reactome-conditional-transition/1.0.0":
        raise RuntimeError("fitted Reactome artifact profile identifier is incompatible")
    if fitted.model_id != "kncc-reactome-conditional-transition-model/1.0.0":
        raise RuntimeError("fitted Reactome artifact model identifier is incompatible")
    pathways = _pathway_profiles()
    counts = _source_model_counts()
    digests = _source_model_digests()
    evaluation = _evaluation_summary()
    licenses = _source_licenses()
    attribution = _source_attribution()
    transformation_notice = str(fitted.source_catalog.provenance["transformation_notice"])
    payload = {
        "algorithm_id": "kncc-reactome-conditional-transition",
        "algorithm_version": "1.0.0",
        "profile_id": "kncc-reactome-conditional-transition/1.0.0",
        "model_id": "kncc-reactome-conditional-transition-model/1.0.0",
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
        "pathways": [pathway.model_dump(mode="json") for pathway in pathways],
        "numpy_version": np.__version__,
        "demo_id": DEMO_ID,
        "demo_request_digest": demo_request_digest(),
        "demo_semantic_oracle_digest": EXPECTED_DEMO_SEMANTIC_ORACLE_DIGEST,
        "source_attribution": attribution,
        "source_licenses": licenses,
        "source_transformation_notice": transformation_notice,
        "safety_class": "research_use_only",
        "claim_ceiling": "conditional_source_cohort_transition_concordance_only",
        "interpretation": (
            "global_adjusted_reactome_membership_coordinate_not_pathway_activation_or_flux"
        ),
        "maximum_evidence_grade": "limited_same_cohort_without_external_validation",
    }
    return LongitudinalGbmReactomeTransitionProfile(
        required_assay_compatibility=REQUIRED_ASSAY_COMPATIBILITY,
        constants=CONSTANTS,
        limits=LIMITS,
        counts=counts,
        digests=digests,
        evaluation=evaluation,
        pathways=pathways,
        numpy_version=np.__version__,
        demo_id=DEMO_ID,
        demo_request_digest=demo_request_digest(),
        demo_semantic_oracle_digest=EXPECTED_DEMO_SEMANTIC_ORACLE_DIGEST,
        source_attribution=attribution,
        source_licenses=licenses,
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
