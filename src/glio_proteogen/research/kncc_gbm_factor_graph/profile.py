"""Content-bound profile for the independent KNCC GBM factor-graph composition."""

from __future__ import annotations

import ast
from functools import lru_cache
from importlib.resources import files
from typing import Final

import numpy as np

from glio_proteogen.research.longitudinal_gbm_kinase_transition.catalog import (
    load_kinase_transition_catalog,
)
from glio_proteogen.research.longitudinal_gbm_kinase_transition.demo import (
    synthetic_demo_request as kinase_demo_request,
)
from glio_proteogen.research.longitudinal_gbm_kinase_transition.profile import (
    algorithm_profile as kinase_algorithm_profile,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.demo import (
    synthetic_demo_request as reactome_demo_request,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.profile import (
    algorithm_profile as reactome_algorithm_profile,
)

from .canonical import canonical_request_digest, profile_payload_digest, sha256_digest
from .contracts import (
    DEMO_ID,
    MODEL_ID,
    PROFILE_ID,
    RELATIONSHIP,
    FactorGraphBlock,
    FactorGraphChildProfileBinding,
    FactorGraphCounts,
    FactorGraphLimits,
    KnccGbmFactorGraphProfile,
    KnccGbmFactorGraphRequest,
)
from .errors import KnccGbmFactorGraphProfileIntegrityError
from .topology import factor_graph_topology

EXPECTED_NUMPY_VERSION: Final = "2.5.2"
_SEMANTIC_SOURCE_FILES: Final = (
    "canonical.py",
    "contracts.py",
    "topology.py",
    "engine.py",
    "service.py",
    "profile.py",
    "demo.py",
)


def _canonical_python_ast(source: bytes) -> str:
    text = source.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return ast.dump(ast.parse(text), annotate_fields=True, include_attributes=False)


def composition_semantic_digest() -> str:
    """Bind the outer canonical and no-cross-block composition semantics."""

    root = files(__package__)
    return sha256_digest(
        {
            name: _canonical_python_ast(root.joinpath(name).read_bytes())
            for name in _SEMANTIC_SOURCE_FILES
        }
    )


def _child_bindings() -> tuple[FactorGraphChildProfileBinding, FactorGraphChildProfileBinding]:
    reactome = reactome_algorithm_profile()
    kinase = kinase_algorithm_profile()
    kinase_catalog = load_kinase_transition_catalog()
    reactome_binding = FactorGraphChildProfileBinding(
        block=FactorGraphBlock.PROTEIN_REACTOME,
        child_profile_id=reactome.profile_id,
        child_profile_digest=reactome.profile_digest,
        source_digest=reactome.digests.source_binding_digest,
        fitted_digest=reactome.digests.fitted_content_digest,
        bootstrap_digest=reactome.digests.bootstrap_ensemble_digest,
        evaluation_digest=reactome.digests.evaluation_digest,
    )
    kinase_binding = FactorGraphChildProfileBinding(
        block=FactorGraphBlock.PHOSPHOSITE_SPHINKS,
        child_profile_id=kinase.profile_id,
        child_profile_digest=kinase.profile_digest,
        source_digest=sha256_digest(kinase_catalog.source_bindings),
        fitted_digest=kinase.digests.fitted_artifact_content_digest,
        bootstrap_digest=kinase.digests.bootstrap_ensemble_digest,
        evaluation_digest=sha256_digest(kinase_catalog.fit_evaluation),
    )
    return reactome_binding, kinase_binding


def _model_derived_demo_request() -> KnccGbmFactorGraphRequest:
    return KnccGbmFactorGraphRequest(
        analysis_id=DEMO_ID,
        reactome_request=reactome_demo_request(),
        kinase_request=kinase_demo_request(),
    )


def _demo_semantic_oracle_digest(
    *,
    reactome_child: FactorGraphChildProfileBinding,
    kinase_child: FactorGraphChildProfileBinding,
    topology_digest: str,
    request_digest: str,
) -> str:
    reactome = reactome_algorithm_profile()
    kinase = kinase_algorithm_profile()
    return sha256_digest(
        {
            "demo_id": DEMO_ID,
            "outer_request_digest": request_digest,
            "relationship": RELATIONSHIP,
            "topology_digest": topology_digest,
            "reactome_child_profile_digest": reactome_child.child_profile_digest,
            "reactome_child_demo_request_digest": reactome.demo_request_digest,
            "reactome_child_demo_semantic_oracle_digest": reactome.demo_semantic_oracle_digest,
            "kinase_child_profile_digest": kinase_child.child_profile_digest,
            "kinase_child_demo_request_digest": kinase.demo_request_digest,
            "kinase_child_demo_semantic_oracle_digest": kinase.demo_semantic_oracle_digest,
            "independent_parallel_blocks": True,
            "cross_modal_fusion_performed": False,
            "numerical_cross_block_edge_count": 0,
        }
    )


def _build_algorithm_profile() -> KnccGbmFactorGraphProfile:
    """Build the profile only after both locked child profiles validate."""

    if np.__version__ != EXPECTED_NUMPY_VERSION:
        raise RuntimeError("KNCC GBM factor graph requires NumPy 2.5.2")
    topology = factor_graph_topology()
    reactome_child, kinase_child = _child_bindings()
    source_inventory_digest = sha256_digest(
        {
            "reactome_child": reactome_child.model_dump(mode="json"),
            "kinase_child": kinase_child.model_dump(mode="json"),
        }
    )
    demo_request_digest = canonical_request_digest(_model_derived_demo_request())
    demo_oracle_digest = _demo_semantic_oracle_digest(
        reactome_child=reactome_child,
        kinase_child=kinase_child,
        topology_digest=topology.topology_digest,
        request_digest=demo_request_digest,
    )
    limits = FactorGraphLimits()
    counts = FactorGraphCounts()
    semantic_digest = composition_semantic_digest()
    payload = {
        "algorithm_id": "glio-ecgi-kncc-gbm-transition",
        "algorithm_version": "1.0.0",
        "profile_id": PROFILE_ID,
        "model_id": MODEL_ID,
        "relationship": RELATIONSHIP,
        "topology": topology.model_dump(mode="json"),
        "topology_digest": topology.topology_digest,
        "reactome_child": reactome_child.model_dump(mode="json"),
        "kinase_child": kinase_child.model_dump(mode="json"),
        "source_inventory_digest": source_inventory_digest,
        "numpy_version": np.__version__,
        "composition_semantic_digest": semantic_digest,
        "limits": limits.model_dump(mode="json"),
        "counts": counts.model_dump(mode="json"),
        "demo_id": DEMO_ID,
        "demo_request_digest": demo_request_digest,
        "demo_semantic_oracle_digest": demo_oracle_digest,
        "source_attestation_state": "verified_exact_child_snapshots",
        "safety_class": "research_use_only",
        "claim_ceiling": "independent_source_cohort_concordance_coordinates_only",
        "research_use_only": True,
        "non_prescriptive": True,
        "independent_parallel_blocks": True,
        "cross_modal_fusion_performed": False,
        "no_numerical_cross_block_edges": True,
    }
    return KnccGbmFactorGraphProfile(
        topology=topology,
        topology_digest=topology.topology_digest,
        reactome_child=reactome_child,
        kinase_child=kinase_child,
        source_inventory_digest=source_inventory_digest,
        numpy_version="2.5.2",
        composition_semantic_digest=semantic_digest,
        limits=limits,
        counts=counts,
        demo_request_digest=demo_request_digest,
        demo_semantic_oracle_digest=demo_oracle_digest,
        source_attestation_state="verified_exact_child_snapshots",
        profile_digest=profile_payload_digest(payload),
    )


@lru_cache(maxsize=1)
def algorithm_profile() -> KnccGbmFactorGraphProfile:
    """Return a cached profile or one sanitized outer integrity failure."""

    try:
        return _build_algorithm_profile()
    except KnccGbmFactorGraphProfileIntegrityError:
        raise
    except Exception as exc:
        raise KnccGbmFactorGraphProfileIntegrityError(
            "a locked KNCC child artifact or outer profile invariant failed"
        ) from exc


__all__ = [
    "EXPECTED_NUMPY_VERSION",
    "algorithm_profile",
    "composition_semantic_digest",
]
