"""Fail-closed development profile for the unfitted GBmap composition model."""

from __future__ import annotations

import ast
from importlib.resources import files
from typing import Final, Literal, Self

import numpy as np
from pydantic import model_validator

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import FrozenModel, Sha256Digest

from .aggregate import (
    MIN_CELLS_PER_DONOR_LABEL,
    MIN_DONORS_PER_LINEAGE,
    MIN_STABLE_GENES_PER_LINEAGE,
    MIN_STUDIES_PER_LINEAGE,
    MIN_UMIS_PER_DONOR_LABEL,
    REFERENCE_EFFECTIVE_DEPTH,
)
from .canonical import profile_digest
from .extraction import (
    EXPECTED_H5PY_VERSION,
    PRODUCTION_GROUPED_DONOR_CATEGORY_COUNT,
    PRODUCTION_GROUPED_STUDY_COUNT,
    PRODUCTION_SOURCE_DONOR_CATEGORY_COUNT,
    PRODUCTION_SOURCE_LABEL_COUNT,
    PRODUCTION_SOURCE_STUDY_CATEGORY_COUNT,
    production_donor_crosswalk,
)
from .feature_identity import (
    EXPECTED_FEATURE_IDENTITY_ARTIFACT_DIGEST,
    EXPECTED_FEATURE_IDENTITY_CONTENT_DIGEST,
    FEATURE_IDENTITY_CROSSWALK_ID,
    production_feature_identity_crosswalk,
)
from .source import (
    CELLXGENE_COLLECTION_ID,
    CELLXGENE_CORE_DATASET_ID,
    CELLXGENE_CORE_DATASET_VERSION_ID,
    EXPECTED_DONOR_CATEGORY_SET_DIGEST,
    SUPPLEMENT_SHA256,
)

ALGORITHM_ID: Final = "gbmap-dm-composition"
ALGORITHM_VERSION: Final = "0.1.0-dev"
PROFILE_ID: Final = "gbmap-dm-composition/0.1.0-dev"
EXPECTED_NUMPY_VERSION: Final = "2.5.2"
VERIFIED_SOURCE_SHA256: Final = (
    "sha256:cb48db2e31299b41d2fe2b6004fadbabe49957bf7d6d72396139db12366ecd8a"
)

# A reviewed source-derived artifact digest is intentionally absent.  A future
# production catalog must require a non-None exact digest and a separate code
# review before any runtime can exist.
EXPECTED_FITTED_ARTIFACT_CONTENT_DIGEST: Final[None] = None

_SEMANTIC_FILES: Final = (
    "aggregate.py",
    "canonical.py",
    "dm.py",
    "errors.py",
    "evaluation.py",
    "extraction.py",
    "feature_identity.py",
    "hierarchy.py",
    "numerics.py",
    "profile.py",
    "selection.py",
    "simplex.py",
    "source.py",
    "splits.py",
    "training.py",
)


class ConditionalSourceExpectation(FrozenModel):
    source_id: Literal["gbmap-core-zenodo-6962901"] = "gbmap-core-zenodo-6962901"
    record_doi: Literal["10.5281/zenodo.6962901"] = "10.5281/zenodo.6962901"
    artifact_name: Literal["scarches_core_GBmap.h5ad"] = "scarches_core_GBmap.h5ad"
    expected_bytes: Literal[8975644082] = 8_975_644_082
    source_md5: Literal["308f143ba384bd9a8acb0fbf2ea005fc"] = "308f143ba384bd9a8acb0fbf2ea005fc"
    cellxgene_collection_id: Literal["999f2a15-3d7e-440b-96ae-2c806799c08c"] = (
        CELLXGENE_COLLECTION_ID
    )
    cellxgene_core_dataset_id: Literal["c888b684-6c51-431f-972a-6c963044cef0"] = (
        CELLXGENE_CORE_DATASET_ID
    )
    cellxgene_core_dataset_version_id: Literal["861acfd8-25f0-418b-a445-aa96da232827"] = (
        CELLXGENE_CORE_DATASET_VERSION_ID
    )
    zenodo_raw_patient_category_count: Literal[113] = PRODUCTION_SOURCE_DONOR_CATEGORY_COUNT
    source_donor_category_count: Literal[110] = PRODUCTION_GROUPED_DONOR_CATEGORY_COUNT
    zenodo_raw_author_category_count: Literal[17] = PRODUCTION_SOURCE_STUDY_CATEGORY_COUNT
    grouped_study_count: Literal[16] = PRODUCTION_GROUPED_STUDY_COUNT
    source_cellid_label_count: Literal[20] = PRODUCTION_SOURCE_LABEL_COUNT
    donor_category_set_digest: Sha256Digest = EXPECTED_DONOR_CATEGORY_SET_DIGEST
    donor_crosswalk_digest: Sha256Digest = production_donor_crosswalk().crosswalk_digest
    publication_prose_patient_count: Literal[109] = 109
    final_supplement_patient_count: Literal[110] = 110
    final_supplement_sha256: Sha256Digest = SUPPLEMENT_SHA256
    donor_count_resolution: Literal["group_113_raw_patient_categories_to_110_reviewed_donors"] = (
        "group_113_raw_patient_categories_to_110_reviewed_donors"
    )
    biological_person_count_claim_permitted: Literal[False] = False
    complete_donor_crosswalk_available: Literal[True] = True
    study_crosswalk_available: Literal[True] = True
    raw_patient_categories_may_be_treated_as_independent_donors: Literal[False] = False
    verified_sha256: Literal[
        "sha256:cb48db2e31299b41d2fe2b6004fadbabe49957bf7d6d72396139db12366ecd8a"
    ] = VERIFIED_SOURCE_SHA256
    exact_source_admitted: Literal[True] = True


class AggregateEligibilityPolicy(FrozenModel):
    effective_depth: Literal[20000] = REFERENCE_EFFECTIVE_DEPTH
    minimum_cells_per_donor_label: Literal[20] = MIN_CELLS_PER_DONOR_LABEL
    minimum_umis_per_donor_label: Literal[20000] = MIN_UMIS_PER_DONOR_LABEL
    minimum_donors_per_lineage: Literal[8] = MIN_DONORS_PER_LINEAGE
    minimum_studies_per_lineage: Literal[3] = MIN_STUDIES_PER_LINEAGE
    minimum_stable_genes_per_lineage: Literal[12] = MIN_STABLE_GENES_PER_LINEAGE
    cell_random_split_forbidden: Literal[True] = True
    donor_and_study_grouping_required: Literal[True] = True


class GbmapDevelopmentProfile(FrozenModel):
    algorithm_id: Literal["gbmap-dm-composition"] = "gbmap-dm-composition"
    algorithm_version: Literal["0.1.0-dev"] = "0.1.0-dev"
    profile_id: Literal["gbmap-dm-composition/0.1.0-dev"] = "gbmap-dm-composition/0.1.0-dev"
    profile_digest: Sha256Digest
    engine_semantic_digest: Sha256Digest
    numpy_version: Literal["2.5.2"] = "2.5.2"
    source_extraction_h5py_version: Literal["3.16.0"] = EXPECTED_H5PY_VERSION
    fit_state: Literal["development_unfitted"] = "development_unfitted"
    source_admission_state: Literal["admitted_private_offline_development_only"] = (
        "admitted_private_offline_development_only"
    )
    expected_fitted_artifact_content_digest: None = None
    feature_identity_state: Literal["admitted_stable_hgnc_crosswalk_only"] = (
        "admitted_stable_hgnc_crosswalk_only"
    )
    feature_identity_crosswalk_id: Literal["gbmap-hgnc-feature-crosswalk/2026-08-28"] = (
        "gbmap-hgnc-feature-crosswalk/2026-08-28"
    )
    feature_identity_artifact_digest: Sha256Digest
    feature_identity_content_digest: Sha256Digest
    source_feature_count: Literal[5000] = 5_000
    stable_hgnc_mapping_count: Literal[4924] = 4_924
    unique_model_eligible_hgnc_count: Literal[4923] = 4_923
    unresolved_feature_count: Literal[76] = 76
    unresolved_feature_in_model_permitted: Literal[False] = False
    source: ConditionalSourceExpectation
    eligibility: AggregateEligibilityPolicy
    intended_output: Literal["reference_constrained_rna_mixture_weights_with_unexplained_mass"] = (
        "reference_constrained_rna_mixture_weights_with_unexplained_mass"
    )
    unknown_component_required: Literal[True] = True
    maximum_support: Literal["limited"] = "limited"
    supported_output_permitted: Literal[False] = False
    model_available: Literal[False] = False
    analysis_runtime_available: Literal[False] = False
    public_http_mounted: Literal[False] = False
    public_cli_mounted: Literal[False] = False
    bundled_fitted_artifact: Literal[False] = False
    histologic_cell_fraction_claim_permitted: Literal[False] = False
    clinical_use_permitted: Literal[False] = False

    @model_validator(mode="after")
    def digest_is_valid(self) -> Self:
        if self.profile_digest != profile_digest(self):
            raise ValueError("profile digest does not match canonical development profile")
        return self


def _canonical_ast(source: bytes) -> str:
    text = source.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return ast.dump(ast.parse(text), annotate_fields=True, include_attributes=False)


def engine_semantic_digest() -> str:
    root = files(__package__)
    return sha256_digest(
        {name: _canonical_ast(root.joinpath(name).read_bytes()) for name in _SEMANTIC_FILES}
    )


def development_profile() -> GbmapDevelopmentProfile:
    """Return a receipt that proves no fitted model or callable runtime exists."""

    if np.__version__ != EXPECTED_NUMPY_VERSION:
        raise RuntimeError("GBmap development core requires NumPy 2.5.2")
    semantic_digest = engine_semantic_digest()
    feature_identity = production_feature_identity_crosswalk()
    source = ConditionalSourceExpectation()
    eligibility = AggregateEligibilityPolicy()
    payload = {
        "algorithm_id": ALGORITHM_ID,
        "algorithm_version": ALGORITHM_VERSION,
        "profile_id": PROFILE_ID,
        "engine_semantic_digest": semantic_digest,
        "numpy_version": np.__version__,
        "source_extraction_h5py_version": EXPECTED_H5PY_VERSION,
        "fit_state": "development_unfitted",
        "source_admission_state": "admitted_private_offline_development_only",
        "expected_fitted_artifact_content_digest": None,
        "feature_identity_state": "admitted_stable_hgnc_crosswalk_only",
        "feature_identity_crosswalk_id": FEATURE_IDENTITY_CROSSWALK_ID,
        "feature_identity_artifact_digest": EXPECTED_FEATURE_IDENTITY_ARTIFACT_DIGEST,
        "feature_identity_content_digest": EXPECTED_FEATURE_IDENTITY_CONTENT_DIGEST,
        "source_feature_count": feature_identity.counts.source_feature_count,
        "stable_hgnc_mapping_count": feature_identity.counts.stable_hgnc_mapping_count,
        "unique_model_eligible_hgnc_count": (
            feature_identity.counts.unique_model_eligible_hgnc_count
        ),
        "unresolved_feature_count": feature_identity.counts.unresolved_count,
        "unresolved_feature_in_model_permitted": False,
        "source": source.model_dump(mode="json"),
        "eligibility": eligibility.model_dump(mode="json"),
        "intended_output": "reference_constrained_rna_mixture_weights_with_unexplained_mass",
        "unknown_component_required": True,
        "maximum_support": "limited",
        "supported_output_permitted": False,
        "model_available": False,
        "analysis_runtime_available": False,
        "public_http_mounted": False,
        "public_cli_mounted": False,
        "bundled_fitted_artifact": False,
        "histologic_cell_fraction_claim_permitted": False,
        "clinical_use_permitted": False,
    }
    return GbmapDevelopmentProfile(
        profile_digest=profile_digest(payload),
        engine_semantic_digest=semantic_digest,
        feature_identity_artifact_digest=EXPECTED_FEATURE_IDENTITY_ARTIFACT_DIGEST,
        feature_identity_content_digest=EXPECTED_FEATURE_IDENTITY_CONTENT_DIGEST,
        source=source,
        eligibility=eligibility,
    )


__all__ = [
    "ALGORITHM_ID",
    "ALGORITHM_VERSION",
    "EXPECTED_FITTED_ARTIFACT_CONTENT_DIGEST",
    "EXPECTED_NUMPY_VERSION",
    "PROFILE_ID",
    "VERIFIED_SOURCE_SHA256",
    "AggregateEligibilityPolicy",
    "ConditionalSourceExpectation",
    "GbmapDevelopmentProfile",
    "development_profile",
    "engine_semantic_digest",
]
