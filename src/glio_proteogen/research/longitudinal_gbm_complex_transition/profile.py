"""Content-bound profile for the fitted GBM participant-transition factor model."""

from __future__ import annotations

import ast
from collections.abc import Mapping
from importlib.resources import files
from typing import Final, cast

import numpy as np
from pydantic import TypeAdapter

from glio_proteogen.research.longitudinal_gbm.catalog import (
    EXPECTED_ELIGIBLE_FEATURE_COUNT,
)

from .canonical import profile_payload_digest, sha256_digest
from .contracts import (
    REQUIRED_ASSAY_COMPATIBILITY,
    ComplexProfileItem,
    ComplexTransitionAlgorithmConstants,
    ComplexTransitionEvaluationSummary,
    ComplexTransitionLimits,
    ComplexTransitionSourceCounts,
    ComplexTransitionSourceDigests,
    LongitudinalGbmComplexTransitionProfile,
    LongitudinalGbmComplexTransitionRequest,
)
from .demo import demo_request_digest
from .fitted_catalog import (
    EXPECTED_NUMPY_VERSION,
    complex_transition_fitted_catalog,
)
from .source_catalog import EXPECTED_GENE_ORDER_DIGEST

_SEMANTIC_SOURCE_FILES: Final = (
    "canonical.py",
    "source_catalog.py",
    "contracts.py",
    "fitted_catalog.py",
    "solver.py",
    "engine.py",
)
CONSTANTS = ComplexTransitionAlgorithmConstants()
LIMITS = ComplexTransitionLimits()


def _canonical_python_ast(source: bytes) -> str:
    text = source.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return ast.dump(
        ast.parse(text),
        annotate_fields=True,
        include_attributes=False,
    )


def engine_semantic_digest() -> str:
    """Bind location-free ASTs that define all runtime numerical semantics."""

    root = files(__package__)
    return sha256_digest(
        {
            name: _canonical_python_ast(root.joinpath(name).read_bytes())
            for name in _SEMANTIC_SOURCE_FILES
        }
    )


def input_contract_schema_digest() -> str:
    return sha256_digest(TypeAdapter(LongitudinalGbmComplexTransitionRequest).json_schema())


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"fitted complex evaluation {name!r} is not an object")
    return cast("Mapping[str, object]", value)


def _number(value: object, name: str) -> float:
    if type(value) not in {int, float}:
        raise RuntimeError(f"fitted complex evaluation {name!r} is not numeric")
    return float(cast("int | float", value))


def _integer(value: object, name: str) -> int:
    if type(value) is not int:
        raise RuntimeError(f"fitted complex evaluation {name!r} is not an integer")
    return value


def _gain_interval() -> tuple[float, float]:
    fitted = complex_transition_fitted_catalog()
    bootstrap = _mapping(
        fitted.evaluation.get("patient_cluster_bootstrap"),
        "patient_cluster_bootstrap",
    )
    raw = bootstrap.get("nominal_90_percent_interval")
    if not isinstance(raw, list) or len(raw) != 2:
        raise RuntimeError("fitted complex gain interval must contain two values")
    return (_number(raw[0], "gain.lower"), _number(raw[1], "gain.upper"))


def _complex_profiles() -> tuple[ComplexProfileItem, ...]:
    fitted = complex_transition_fitted_catalog()
    gain_interval = _gain_interval()
    return tuple(
        ComplexProfileItem(
            complex_index=model.complex_index,
            domain_id=model.domain_id,
            reactome_id=model.reactome_id,
            complex_name=model.name,
            family_id=source.ablation_family_id,
            selection_tier=source.selection_tier,
            mapped_member_count=len(source.member_feature_indices),
            fitted_member_count=model.member_slot_count,
            source_held_member_relative_gain=(
                model.evaluation.relative_mae_gain_vs_training_center
            ),
            source_panel_patient_cluster_gain_90_interval=gain_interval,
            source_direction_accuracy=model.evaluation.direction_accuracy,
            minimum_outer_loading_cosine=model.evaluation.minimum_loading_cosine,
        )
        for model, source in zip(
            fitted.complexes,
            fitted.source_catalog.complexes,
            strict=True,
        )
    )


def _source_counts() -> ComplexTransitionSourceCounts:
    fitted = complex_transition_fitted_catalog()
    source = fitted.source_catalog
    return ComplexTransitionSourceCounts(
        source_gene_count=len(source.genes),
        eligible_source_gene_count=EXPECTED_ELIGIBLE_FEATURE_COUNT,
        complex_count=len(source.complexes),
        total_member_count=sum(item.member_slot_count for item in fitted.complexes),
        unique_member_gene_count=len(fitted.union_feature_indices),
        nested_family_count=len(source.ablation_families),
        fitted_bootstrap_replicate_count=fitted.bootstrap_replicate_count,
    )


def _source_digests() -> ComplexTransitionSourceDigests:
    fitted = complex_transition_fitted_catalog()
    source = fitted.source_catalog
    return ComplexTransitionSourceDigests(
        source_catalog_artifact_digest=source.artifact_byte_digest,
        source_catalog_content_digest=source.content_digest,
        source_binding_digest=source.source_binding_digest,
        panel_selection_digest=source.selection_digest,
        participant_membership_digest=source.complex_membership_digest,
        overlap_control_digest=source.overlap_control_digest,
        gene_order_digest=EXPECTED_GENE_ORDER_DIGEST,
        fitted_artifact_digest=fitted.artifact_byte_digest,
        fitted_content_digest=fitted.content_digest,
        reference_loading_digest=fitted.reference_loading_digest,
        bootstrap_ensemble_digest=fitted.bootstrap_ensemble_digest,
        bootstrap_seed_namespace_digest=fitted.bootstrap_seed_namespace_digest,
        training_recipe_digest=fitted.training_recipe_digest,
        fold_policy_digest=fitted.fold_policy_digest,
        source_processing_ablation_digest=fitted.source_processing_ablation_digest,
        evaluation_digest=fitted.evaluation_digest,
        demo_request_digest=demo_request_digest(),
        input_contract_schema_digest=input_contract_schema_digest(),
        engine_semantic_digest=engine_semantic_digest(),
    )


def _evaluation_summary() -> ComplexTransitionEvaluationSummary:
    evaluation = complex_transition_fitted_catalog().evaluation
    nonconvergence = _mapping(
        evaluation.get("nonconvergence_counts"),
        "nonconvergence_counts",
    )
    return ComplexTransitionEvaluationSummary(
        validation_scope="internal_patient_grouped_held_member_reconstruction",
        patient_count=104,
        evaluation_count=_integer(evaluation.get("evaluation_count"), "evaluation_count"),
        zero_transition_mean_standardized_mae=_number(
            evaluation.get("zero_transition_standardized_mae"),
            "zero_transition_standardized_mae",
        ),
        training_center_mean_standardized_mae=_number(
            evaluation.get("training_center_standardized_mae"),
            "training_center_standardized_mae",
        ),
        factor_model_mean_standardized_mae=_number(
            evaluation.get("model_standardized_mae"),
            "model_standardized_mae",
        ),
        mean_relative_gain_over_training_center=_number(
            evaluation.get("relative_mae_gain_vs_training_center"),
            "relative_mae_gain_vs_training_center",
        ),
        patient_cluster_median_gain_90_interval=_gain_interval(),
        held_member_direction_accuracy=_number(
            evaluation.get("direction_accuracy"),
            "direction_accuracy",
        ),
        minimum_outer_loading_cosine=_number(
            evaluation.get("minimum_outer_loading_cosine"),
            "minimum_outer_loading_cosine",
        ),
        nonconverged_reference_fit_count=_integer(
            nonconvergence.get("factor"),
            "nonconvergence.factor",
        ),
        nonconverged_outer_fit_count=(
            _integer(
                nonconvergence.get("preprocessing"),
                "nonconvergence.preprocessing",
            )
            + _integer(
                nonconvergence.get("held_coordinate"),
                "nonconvergence.held_coordinate",
            )
        ),
    )


def algorithm_profile() -> LongitudinalGbmComplexTransitionProfile:
    """Return the immutable profile only after source and fitted locks validate."""

    if np.__version__ != EXPECTED_NUMPY_VERSION:
        raise RuntimeError("complex transition factor model requires NumPy 2.5.2")
    fitted = complex_transition_fitted_catalog()
    if fitted.numpy_version != EXPECTED_NUMPY_VERSION:
        raise RuntimeError("fitted complex transition NumPy version is incompatible")
    source = fitted.source_catalog
    complexes = _complex_profiles()
    counts = _source_counts()
    digests = _source_digests()
    evaluation = _evaluation_summary()
    source_licenses = (
        f"PDC000514 article/data: {source.provenance['pdc_license']}",
        f"Reactome annotation: {source.provenance['reactome_annotation_license']}",
        f"HGNC identifiers: {source.provenance['hgnc_license']}",
    )
    draft = LongitudinalGbmComplexTransitionProfile.model_construct(
        algorithm_id="kncc-reactome-complex-transition",
        algorithm_version="1.0.0",
        profile_id="kncc-reactome-complex-transition/1.0.0",
        model_id="kncc-reactome-complex-transition-factor-model/1.0.0",
        profile_digest="sha256:" + "0" * 64,
        required_assay_compatibility=REQUIRED_ASSAY_COMPATIBILITY,
        numpy_version=EXPECTED_NUMPY_VERSION,
        constants=CONSTANTS,
        limits=LIMITS,
        counts=counts,
        digests=digests,
        evaluation=evaluation,
        complexes=complexes,
        source_licenses=source_licenses,
        source_attribution=(
            f"{source.provenance['pdc_article']}; "
            f"{source.provenance['reactome_resource']} release 97."
        ),
        claim_ceiling=("source_cohort_reactome_participant_set_transition_concordance_only"),
        limitations=tuple(dict.fromkeys((*source.limitations, *fitted.limitations))),
        research_use_only=True,
        non_prescriptive=True,
    )
    document = draft.model_dump(mode="python")
    document["profile_digest"] = profile_payload_digest(document)
    return LongitudinalGbmComplexTransitionProfile.model_validate(document, strict=True)


__all__ = [
    "CONSTANTS",
    "LIMITS",
    "algorithm_profile",
    "engine_semantic_digest",
    "input_contract_schema_digest",
]
