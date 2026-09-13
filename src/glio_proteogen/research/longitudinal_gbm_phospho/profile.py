"""Content-bound runtime profile for the PDC000515 phosphosite lane."""

from __future__ import annotations

import ast
from importlib.resources import files
from typing import Final

import numpy as np

from .canonical import profile_payload_digest, sha256_digest
from .catalog import MODEL_ID, load_phosphosite_transition_catalog
from .contracts import (
    REQUIRED_ASSAY_COMPATIBILITY,
    AlgorithmConstants,
    LongitudinalGbmPhosphoProfile,
    SourceModelCounts,
    SourceModelDigests,
    SourceModelQualityGates,
    SphinksCrosswalkProvenance,
)
from .demo import DEMO_ID, DEMO_SEMANTIC_ORACLE_DIGEST, demo_request_digest
from .errors import SourceProfileIntegrityError

EXPECTED_NUMPY_VERSION: Final = "2.5.2"
_SEMANTIC_SOURCE_FILES: Final = ("canonical.py", "catalog.py", "contracts.py", "engine.py")

CONSTANTS = AlgorithmConstants(
    transition_projection="frozen_sparse_l1_raw_delta_over_source_scale_v1",
    missing_evidence_policy="missing_and_unsupported_never_become_negative_v1",
    censoring_policy="one_sided_bounds_retained_but_excluded_from_point_projection_v1",
    coefficient_uncertainty_policy=(
        "exact_patient_bootstrap_full_huber_refit_replicate_scales_release_eligible_reselection_v2"
    ),
    measurement_uncertainty_policy=(
        "deterministic_quality_scaled_gaussian_reported_value_perturbation_v1"
    ),
    measurement_covariance_policy=(
        "featurewise_independent_gaussian_from_to_se_quadrature_no_shared_reference_covariance_v1"
    ),
    uncertainty_interaction_policy="paired_full_model_bootstrap_interaction_decomposition_v1",
    composite_site_policy="source_site_groups_indivisible_v1",
)


def _canonical_python_ast(source: bytes) -> str:
    text = source.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return ast.dump(ast.parse(text), annotate_fields=True, include_attributes=False)


def engine_semantic_digest() -> str:
    root = files(__package__)
    return sha256_digest(
        {
            name: _canonical_python_ast(root.joinpath(name).read_bytes())
            for name in _SEMANTIC_SOURCE_FILES
        }
    )


def algorithm_profile() -> LongitudinalGbmPhosphoProfile:
    if np.__version__ != EXPECTED_NUMPY_VERSION:
        raise RuntimeError("KNCC longitudinal phosphosite concordance requires NumPy 2.5.2")
    catalog = load_phosphosite_transition_catalog()
    if REQUIRED_ASSAY_COMPATIBILITY.source_profile_digest != catalog.source_profile_digest:
        raise SourceProfileIntegrityError("assay attestation is not bound to the source profile")
    if REQUIRED_ASSAY_COMPATIBILITY.source_artifact_content_digest != catalog.artifact_digest:
        raise SourceProfileIntegrityError("assay attestation is not bound to the source artifact")
    counts = SourceModelCounts(selected_feature_count=catalog.selected_feature_count)
    digests = SourceModelDigests(
        source_artifact_content_digest=catalog.artifact_digest,
        source_artifact_byte_digest=catalog.artifact_sha256,
        source_profile_digest=catalog.source_profile_digest,
        source_manifest_digest=catalog.source_manifest_digest,
        bootstrap_ensemble_digest=catalog.bootstrap_digest,
        sphinks_crosswalk_digest=catalog.crosswalk_digest,
        hgnc_mapping_digest=catalog.hgnc_mapping_digest,
        engine_semantic_digest=engine_semantic_digest(),
    )
    gates = SourceModelQualityGates(
        selection_stability_passed=catalog.selection_stability_gate_passed,
        bootstrap_full_refit_passed=catalog.bootstrap_full_refit_gate_passed,
        bootstrap_feature_selection_stability_passed=(
            catalog.bootstrap_feature_selection_stability_gate_passed
        ),
        bootstrap_calibration_passed=catalog.bootstrap_calibration_gate_passed,
    )
    sphinks_provenance = SphinksCrosswalkProvenance(
        article_attribution=catalog.sphinks_source_attribution,
        transformation_notice=catalog.sphinks_transformation_notice,
    )
    payload = {
        "algorithm_id": "kncc-gbm-longitudinal-phosphosite-concordance",
        "algorithm_version": "1.0.0",
        "profile_id": "kncc-gbm-longitudinal-phosphosite-concordance/1.0.0",
        "model_id": MODEL_ID,
        "required_assay_compatibility": REQUIRED_ASSAY_COMPATIBILITY.model_dump(mode="json"),
        "constants": CONSTANTS.model_dump(mode="json"),
        "counts": counts.model_dump(mode="json"),
        "digests": digests.model_dump(mode="json"),
        "quality_gates": gates.model_dump(mode="json"),
        "numpy_version": np.__version__,
        "demo_id": DEMO_ID,
        "demo_request_digest": demo_request_digest(),
        "demo_semantic_oracle_digest": DEMO_SEMANTIC_ORACLE_DIGEST,
        "source_attribution": catalog.source_attribution,
        "source_license": catalog.source_license,
        "source_license_url": catalog.source_license_url,
        "source_transformation_notice": catalog.source_transformation_notice,
        "sphinks_crosswalk_provenance": sphinks_provenance.model_dump(mode="json"),
        "source_attestation_state": catalog.source_attestation_state,
        "safety_class": "research_use_only",
        "claim_ceiling": "raw_phosphosite_transition_concordance_only",
    }
    return LongitudinalGbmPhosphoProfile(
        model_id=MODEL_ID,
        required_assay_compatibility=REQUIRED_ASSAY_COMPATIBILITY,
        constants=CONSTANTS,
        counts=counts,
        digests=digests,
        quality_gates=gates,
        numpy_version=np.__version__,
        demo_id=DEMO_ID,
        demo_request_digest=demo_request_digest(),
        demo_semantic_oracle_digest=DEMO_SEMANTIC_ORACLE_DIGEST,
        source_attribution=catalog.source_attribution,
        source_license=catalog.source_license,
        source_license_url=catalog.source_license_url,
        source_transformation_notice=catalog.source_transformation_notice,
        sphinks_crosswalk_provenance=sphinks_provenance,
        source_attestation_state="verified_exact_snapshots",
        profile_digest=profile_payload_digest(payload),
    )


__all__ = [
    "CONSTANTS",
    "EXPECTED_NUMPY_VERSION",
    "algorithm_profile",
    "engine_semantic_digest",
]
