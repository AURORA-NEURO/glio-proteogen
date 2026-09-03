"""Content-bound runtime profile for signature-transition concordance."""

from __future__ import annotations

import ast
from importlib.resources import files
from typing import Final

import numpy as np

from glio_proteogen.research.longitudinal_gbm_phospho.contracts import (
    REQUIRED_ASSAY_COMPATIBILITY,
)

from .canonical import profile_payload_digest, sha256_digest
from .catalog import MODEL_ID, load_kinase_transition_catalog
from .contracts import (
    AlgorithmConstants,
    LongitudinalGbmKinaseTransitionProfile,
    SourceModelCounts,
    SourceModelDigests,
    SourceProvenance,
    SourceQualityGates,
)
from .demo import DEMO_ID, DEMO_SEMANTIC_ORACLE_DIGEST, demo_request_digest

EXPECTED_NUMPY_VERSION: Final = "2.5.2"
_SEMANTIC_SOURCE_FILES: Final = ("canonical.py", "catalog.py", "contracts.py", "engine.py")
CONSTANTS = AlgorithmConstants()


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


def algorithm_profile() -> LongitudinalGbmKinaseTransitionProfile:
    if np.__version__ != EXPECTED_NUMPY_VERSION:
        raise RuntimeError("signature-transition concordance requires NumPy 2.5.2")
    catalog = load_kinase_transition_catalog()
    counts = SourceModelCounts()
    bindings = catalog.source_bindings
    digests = SourceModelDigests(
        fitter_source_sha256=bindings["fitter_source_sha256"],
        fitted_artifact_content_digest=catalog.artifact_digest,
        fitted_artifact_byte_digest=catalog.artifact_sha256,
        bootstrap_ensemble_digest=catalog.bootstrap_digest,
        pdc_phosphosite_artifact_content_digest=bindings["pdc_phosphosite_artifact_content_digest"],
        pdc_phosphosite_source_profile_digest=bindings["pdc_phosphosite_source_profile_digest"],
        pdc_source_manifest_digest=bindings["pdc_source_manifest_digest"],
        pdc_hgnc_mapping_digest=bindings["pdc_hgnc_mapping_digest"],
        pdc_sphinks_crosswalk_digest=bindings["pdc_sphinks_crosswalk_digest"],
        sphinks_catalog_artifact_digest=bindings["sphinks_catalog_artifact_digest"],
        sphinks_catalog_content_digest=bindings["sphinks_catalog_content_digest"],
        sphinks_background_tuple_digest=bindings["sphinks_background_tuple_digest"],
        sphinks_signature_edge_digest=bindings["sphinks_signature_edge_digest"],
        sphinks_master_kinase_digest=bindings["sphinks_master_kinase_digest"],
        sphinks_source_sha256=bindings["sphinks_source_sha256"],
        engine_semantic_digest=engine_semantic_digest(),
    )
    source = SourceProvenance(
        pdc_article_attribution=catalog.pdc_attribution,
        pdc_license="CC-BY-4.0",
        pdc_license_url="https://creativecommons.org/licenses/by/4.0/",
        pdc_transformation_notice=catalog.pdc_transformation_notice,
        sphinks_article_attribution=catalog.sphinks_attribution,
        sphinks_license="CC-BY-4.0",
        sphinks_license_url="https://creativecommons.org/licenses/by/4.0/",
        sphinks_transformation_notice=catalog.sphinks_transformation_notice,
    )
    payload: dict[str, object] = {
        "algorithm_id": "kncc-gbm-longitudinal-kinase-transition",
        "algorithm_version": "1.0.0",
        "profile_id": "kncc-gbm-longitudinal-kinase-transition/1.0.0",
        "model_id": MODEL_ID,
        "required_assay_compatibility": REQUIRED_ASSAY_COMPATIBILITY.model_dump(mode="json"),
        "constants": CONSTANTS.model_dump(mode="json"),
        "counts": counts.model_dump(mode="json"),
        "digests": digests.model_dump(mode="json"),
        "quality_gates": SourceQualityGates().model_dump(mode="json"),
        "source_provenance": source.model_dump(mode="json"),
        "numpy_version": np.__version__,
        "demo_id": DEMO_ID,
        "demo_request_digest": demo_request_digest(),
        "demo_semantic_oracle_digest": DEMO_SEMANTIC_ORACLE_DIGEST,
        "source_attestation_state": "verified_exact_snapshots",
        "safety_class": "research_use_only",
        "claim_ceiling": "SPHINKS_signature_transition_concordance_only",
    }
    return LongitudinalGbmKinaseTransitionProfile(
        model_id=MODEL_ID,
        required_assay_compatibility=REQUIRED_ASSAY_COMPATIBILITY,
        constants=CONSTANTS,
        counts=counts,
        digests=digests,
        quality_gates=SourceQualityGates(),
        source_provenance=source,
        numpy_version=np.__version__,
        demo_id=DEMO_ID,
        demo_request_digest=demo_request_digest(),
        demo_semantic_oracle_digest=DEMO_SEMANTIC_ORACLE_DIGEST,
        source_attestation_state="verified_exact_snapshots",
        profile_digest=profile_payload_digest(payload),
    )


__all__ = [
    "CONSTANTS",
    "EXPECTED_NUMPY_VERSION",
    "algorithm_profile",
    "engine_semantic_digest",
]
