"""Route-derived deployment catalog coverage."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, cast

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.middleware.gzip import GZipMiddleware
from tools.validate_operation_catalog import (
    OperationCatalogValidationError,
    run_repository_validation,
    validate_operation_catalog,
)

from glio_proteogen.adapters.gbm_factor_graph import (
    GBM_FACTOR_GRAPH_REPLAY_MAX_BYTES,
    GBM_FACTOR_GRAPH_REQUEST_MAX_BYTES,
    GBM_FACTOR_GRAPH_RESULT_MAX_BYTES,
)
from glio_proteogen.adapters.gbm_functional_proteotype import (
    GBM_FUNCTIONAL_PROTEOTYPE_REPLAY_MAX_BYTES,
    GBM_FUNCTIONAL_PROTEOTYPE_REQUEST_MAX_BYTES,
    GBM_FUNCTIONAL_PROTEOTYPE_RESULT_MAX_BYTES,
)
from glio_proteogen.adapters.gbm_master_kinases import (
    GBM_MASTER_KINASES_REPLAY_MAX_BYTES,
    GBM_MASTER_KINASES_REQUEST_MAX_BYTES,
    GBM_MASTER_KINASES_RESULT_MAX_BYTES,
)
from glio_proteogen.adapters.gbm_rna_purity import (
    GBM_RNA_PURITY_REPLAY_MAX_BYTES,
    GBM_RNA_PURITY_REQUEST_MAX_BYTES,
    GBM_RNA_PURITY_RESULT_MAX_BYTES,
)
from glio_proteogen.adapters.glioma_models import (
    GBM_AXES_REPLAY_MAX_BYTES,
    GBM_AXES_REQUEST_MAX_BYTES,
    GBM_AXES_RESULT_MAX_BYTES,
)
from glio_proteogen.adapters.longitudinal_gbm import (
    LONGITUDINAL_GBM_REPLAY_MAX_BYTES,
    LONGITUDINAL_GBM_REQUEST_MAX_BYTES,
    LONGITUDINAL_GBM_RESULT_MAX_BYTES,
    M15_LONGITUDINAL_RECURRENCE_ROUTE_PREFIX,
)
from glio_proteogen.adapters.longitudinal_gbm_complex_transition import (
    LONGITUDINAL_GBM_COMPLEX_TRANSITION_REPLAY_MAX_BYTES,
    LONGITUDINAL_GBM_COMPLEX_TRANSITION_REQUEST_MAX_BYTES,
    LONGITUDINAL_GBM_COMPLEX_TRANSITION_RESULT_MAX_BYTES,
    M09_COMPLEX_TRANSITION_REPLAY_MAX_BYTES,
    M09_COMPLEX_TRANSITION_REQUEST_MAX_BYTES,
    M09_COMPLEX_TRANSITION_RESULT_MAX_BYTES,
    M09_COMPLEX_TRANSITION_ROUTE_PREFIX,
)
from glio_proteogen.adapters.longitudinal_gbm_kinase_transition import (
    LONGITUDINAL_GBM_KINASE_TRANSITION_REPLAY_MAX_BYTES,
    LONGITUDINAL_GBM_KINASE_TRANSITION_REQUEST_MAX_BYTES,
    LONGITUDINAL_GBM_KINASE_TRANSITION_RESULT_MAX_BYTES,
)
from glio_proteogen.adapters.longitudinal_gbm_neftel_transition import (
    LONGITUDINAL_GBM_NEFTEL_TRANSITION_REPLAY_MAX_BYTES,
    LONGITUDINAL_GBM_NEFTEL_TRANSITION_REQUEST_MAX_BYTES,
    LONGITUDINAL_GBM_NEFTEL_TRANSITION_RESULT_MAX_BYTES,
)
from glio_proteogen.adapters.longitudinal_gbm_phospho import (
    LONGITUDINAL_GBM_PHOSPHO_REPLAY_MAX_BYTES,
    LONGITUDINAL_GBM_PHOSPHO_REQUEST_MAX_BYTES,
    LONGITUDINAL_GBM_PHOSPHO_RESULT_MAX_BYTES,
)
from glio_proteogen.adapters.longitudinal_gbm_reactome_transition import (
    LONGITUDINAL_GBM_REACTOME_TRANSITION_REPLAY_MAX_BYTES,
    LONGITUDINAL_GBM_REACTOME_TRANSITION_REQUEST_MAX_BYTES,
    LONGITUDINAL_GBM_REACTOME_TRANSITION_RESULT_MAX_BYTES,
)
from glio_proteogen.adapters.m10_functional_proteotype_facade import (
    M10_FUNCTIONAL_PROTEOTYPE_REPLAY_MAX_BYTES,
    M10_FUNCTIONAL_PROTEOTYPE_REQUEST_MAX_BYTES,
    M10_FUNCTIONAL_PROTEOTYPE_RESULT_MAX_BYTES,
)
from glio_proteogen.adapters.m11_protein_native_subtype_facade import (
    M11_PROTEIN_NATIVE_SUBTYPE_REPLAY_MAX_BYTES,
    M11_PROTEIN_NATIVE_SUBTYPE_REQUEST_MAX_BYTES,
    M11_PROTEIN_NATIVE_SUBTYPE_RESULT_MAX_BYTES,
)
from glio_proteogen.adapters.m14_microenvironment_protein_programs_facade import (
    M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_DEMO_ID,
    M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_REPLAY_MAX_BYTES,
    M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_REQUEST_MAX_BYTES,
    M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_RESULT_MAX_BYTES,
)
from glio_proteogen.adapters.neftel_programs import (
    NEFTEL_PROGRAMS_REPLAY_MAX_BYTES,
    NEFTEL_PROGRAMS_REQUEST_MAX_BYTES,
    NEFTEL_PROGRAMS_RESULT_MAX_BYTES,
)
from glio_proteogen.adapters.research_state import (
    RESEARCH_STATE_REPLAY_MAX_BYTES,
    RESEARCH_STATE_REQUEST_MAX_BYTES,
    RESEARCH_STATE_RESULT_MAX_BYTES,
)
from glio_proteogen.deployment import (
    DeploymentConfigurationError,
    DeploymentSettings,
    _operation_catalog,
    create_deployment_app,
)
from glio_proteogen.research.gbm_functional_proteotype.demo import (
    DEMO_ID as FUNCTIONAL_PROTEOTYPE_DEMO_ID,
)
from glio_proteogen.research.gbm_master_kinases import DEMO_ID as MASTER_KINASE_DEMO_ID
from glio_proteogen.research.gbm_proteomic_axes import DEMO_ID as GBM_DEMO_ID
from glio_proteogen.research.gbm_rna_purity.demo import DEMO_ID as GBM_RNA_PURITY_DEMO_ID
from glio_proteogen.research.kncc_gbm_factor_graph.contracts import (
    DEMO_ID as FACTOR_GRAPH_DEMO_ID,
)
from glio_proteogen.research.longitudinal_gbm.demo import DEMO_ID as LONGITUDINAL_DEMO_ID
from glio_proteogen.research.longitudinal_gbm_complex_transition.demo import (
    DEMO_ID as LONGITUDINAL_COMPLEX_TRANSITION_DEMO_ID,
)
from glio_proteogen.research.longitudinal_gbm_kinase_transition.demo import (
    DEMO_ID as LONGITUDINAL_KINASE_TRANSITION_DEMO_ID,
)
from glio_proteogen.research.longitudinal_gbm_neftel_transition.demo import (
    DEMO_ID as LONGITUDINAL_NEFTEL_TRANSITION_DEMO_ID,
)
from glio_proteogen.research.longitudinal_gbm_phospho.demo import (
    DEMO_ID as LONGITUDINAL_PHOSPHO_DEMO_ID,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.demo import (
    DEMO_ID as LONGITUDINAL_REACTOME_TRANSITION_DEMO_ID,
)
from glio_proteogen.research.neftel_protein_programs import DEMO_ID as NEFTEL_DEMO_ID
from glio_proteogen.research.proteogenomic_state import DEMO_ID

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_OK = 200
_HTTP_PAYLOAD_TOO_LARGE = 413
_HTTP_UNPROCESSABLE = 422
_CATALOG_VERSION = 2
_APPLICATION_DEFAULT_REQUEST_MAX_BYTES = 4 * 1024 * 1024
_M1901_RESULT_MAX_BYTES = 8 * 1024 * 1024
_V1_COMPATIBILITY_CATALOG_DIGEST = (
    "sha256:48ba3c1afe276c5bffc66cb0d1927a0e85d057612f275aca165d47919d4111b6"
)


def _assert_exhaustive_report(report: dict[str, object], digest: str) -> None:
    assert report == {
        "valid": True,
        "catalog_digest": digest,
        "mounted_operation_count": 421,
        "mounted_route_registration_count": 421,
        "shadowed_route_registration_count": 0,
        "catalog_operation_count": 421,
        "method_counts": {"GET": 195, "POST": 226},
        "safety_class_counts": {
            "S2": 157,
            "S3": 187,
            "operational": 5,
            "research-use-only": 72,
        },
        "request_media_type_counts": {
            "application/json": 225,
            "application/octet-stream": 1,
        },
        "response_media_type_counts": {"application/json": 421},
        "request_limit_declared_count": 226,
        "result_limit_declared_count": 290,
        "validated_example_status_counts": {"abstained": 403, "validated": 18},
        "validated_example_abstention_reason_counts": {
            "no_repository_validated_fixture": 138,
            "operation_has_no_request_body": 195,
            "requires_prior_operation_result": 70,
        },
    }


def _assert_research_metadata(operations: dict[tuple[str, str], dict[str, object]]) -> None:
    analyze = operations[("POST", "/v1/research/proteogenomic-state/analyze")]
    assert analyze["request_max_bytes"] == RESEARCH_STATE_REQUEST_MAX_BYTES
    assert analyze["result_max_bytes"] == RESEARCH_STATE_RESULT_MAX_BYTES
    assert analyze["safety_class"] == "research-use-only"
    assert analyze["mutability_class"] == "stateless-compute"
    assert analyze["validated_example_status"] == "validated"
    assert analyze["validated_example_id"] == DEMO_ID
    assert analyze["validated_example_abstention_reason"] is None
    verify = operations[("POST", "/v1/research/proteogenomic-state/verify")]
    assert verify["request_max_bytes"] == RESEARCH_STATE_REPLAY_MAX_BYTES
    assert verify["result_max_bytes"] == RESEARCH_STATE_REPLAY_MAX_BYTES
    assert verify["validated_example_status"] == "abstained"
    assert verify["validated_example_id"] is None
    assert verify["validated_example_abstention_reason"] == "requires_prior_operation_result"
    profile = operations[("GET", "/v1/research/proteogenomic-state/profile")]
    demo = operations[("GET", "/v1/research/proteogenomic-state/demo")]
    assert profile["request_max_bytes"] is None
    assert demo["request_max_bytes"] is None
    assert profile["result_max_bytes"] == RESEARCH_STATE_RESULT_MAX_BYTES
    assert demo["result_max_bytes"] == RESEARCH_STATE_RESULT_MAX_BYTES
    assert profile["validated_example_status"] == "abstained"
    assert profile["validated_example_id"] is None
    assert profile["validated_example_abstention_reason"] == "operation_has_no_request_body"

    gbm_analyze = operations[("POST", "/v1/research/gbm-proteomic-axes/analyze")]
    assert gbm_analyze["request_max_bytes"] == GBM_AXES_REQUEST_MAX_BYTES
    assert gbm_analyze["result_max_bytes"] == GBM_AXES_RESULT_MAX_BYTES
    assert gbm_analyze["safety_class"] == "research-use-only"
    assert gbm_analyze["mutability_class"] == "stateless-compute"
    assert gbm_analyze["validated_example_status"] == "validated"
    assert gbm_analyze["validated_example_id"] == GBM_DEMO_ID
    gbm_verify = operations[("POST", "/v1/research/gbm-proteomic-axes/verify")]
    assert gbm_verify["request_max_bytes"] == GBM_AXES_REPLAY_MAX_BYTES
    assert gbm_verify["result_max_bytes"] == GBM_AXES_REPLAY_MAX_BYTES

    neftel_analyze = operations[("POST", "/v1/research/neftel-protein-programs/analyze")]
    assert neftel_analyze["request_max_bytes"] == NEFTEL_PROGRAMS_REQUEST_MAX_BYTES
    assert neftel_analyze["result_max_bytes"] == NEFTEL_PROGRAMS_RESULT_MAX_BYTES
    assert neftel_analyze["safety_class"] == "research-use-only"
    assert neftel_analyze["mutability_class"] == "stateless-compute"
    assert neftel_analyze["validated_example_status"] == "validated"
    assert neftel_analyze["validated_example_id"] == NEFTEL_DEMO_ID
    neftel_verify = operations[("POST", "/v1/research/neftel-protein-programs/verify")]
    assert neftel_verify["request_max_bytes"] == NEFTEL_PROGRAMS_REPLAY_MAX_BYTES
    assert neftel_verify["result_max_bytes"] == NEFTEL_PROGRAMS_REPLAY_MAX_BYTES

    for assertion in (
        _assert_master_kinase_metadata,
        _assert_gbm_rna_purity_metadata,
        _assert_functional_proteotype_metadata,
        _assert_longitudinal_metadata,
        _assert_longitudinal_phospho_metadata,
        _assert_longitudinal_kinase_transition_metadata,
        _assert_longitudinal_neftel_transition_metadata,
        _assert_longitudinal_reactome_transition_metadata,
        _assert_longitudinal_complex_transition_metadata,
        _assert_factor_graph_metadata,
        _assert_m09_facade_metadata,
        _assert_m10_facade_metadata,
        _assert_m11_facade_metadata,
        _assert_m14_facade_metadata,
        _assert_m15_facade_metadata,
    ):
        assertion(operations)


def _assert_functional_proteotype_metadata(
    operations: dict[tuple[str, str], dict[str, object]],
) -> None:
    prefix = "/v1/research/gbm-functional-proteotype"
    analyze = operations[("POST", f"{prefix}/analyze")]
    assert analyze["request_max_bytes"] == GBM_FUNCTIONAL_PROTEOTYPE_REQUEST_MAX_BYTES
    assert analyze["result_max_bytes"] == GBM_FUNCTIONAL_PROTEOTYPE_RESULT_MAX_BYTES
    assert analyze["safety_class"] == "research-use-only"
    assert analyze["mutability_class"] == "stateless-compute"
    assert analyze["validated_example_status"] == "validated"
    assert analyze["validated_example_id"] == FUNCTIONAL_PROTEOTYPE_DEMO_ID
    assert analyze["validated_example_abstention_reason"] is None
    verify = operations[("POST", f"{prefix}/verify")]
    assert verify["request_max_bytes"] == GBM_FUNCTIONAL_PROTEOTYPE_REPLAY_MAX_BYTES
    assert verify["result_max_bytes"] == GBM_FUNCTIONAL_PROTEOTYPE_RESULT_MAX_BYTES
    assert verify["validated_example_status"] == "abstained"
    assert verify["validated_example_abstention_reason"] == "requires_prior_operation_result"
    for suffix in ("profile", "demo"):
        operation = operations[("GET", f"{prefix}/{suffix}")]
        assert operation["request_max_bytes"] is None
        assert operation["result_max_bytes"] == GBM_FUNCTIONAL_PROTEOTYPE_RESULT_MAX_BYTES


def _assert_master_kinase_metadata(
    operations: dict[tuple[str, str], dict[str, object]],
) -> None:
    master_analyze = operations[("POST", "/v1/research/gbm-master-kinases/analyze")]
    assert master_analyze["request_max_bytes"] == GBM_MASTER_KINASES_REQUEST_MAX_BYTES
    assert master_analyze["result_max_bytes"] == GBM_MASTER_KINASES_RESULT_MAX_BYTES
    assert master_analyze["safety_class"] == "research-use-only"
    assert master_analyze["mutability_class"] == "stateless-compute"
    assert master_analyze["validated_example_status"] == "validated"
    assert master_analyze["validated_example_id"] == MASTER_KINASE_DEMO_ID
    master_verify = operations[("POST", "/v1/research/gbm-master-kinases/verify")]
    assert master_verify["request_max_bytes"] == GBM_MASTER_KINASES_REPLAY_MAX_BYTES
    assert master_verify["result_max_bytes"] == GBM_MASTER_KINASES_REPLAY_MAX_BYTES


def _assert_gbm_rna_purity_metadata(
    operations: dict[tuple[str, str], dict[str, object]],
) -> None:
    prefix = "/v1/research/gbm-rna-purity"
    analyze = operations[("POST", f"{prefix}/analyze")]
    assert analyze["request_max_bytes"] == GBM_RNA_PURITY_REQUEST_MAX_BYTES
    assert analyze["result_max_bytes"] == GBM_RNA_PURITY_RESULT_MAX_BYTES
    assert analyze["safety_class"] == "research-use-only"
    assert analyze["mutability_class"] == "stateless-compute"
    assert analyze["validated_example_status"] == "validated"
    assert analyze["validated_example_id"] == GBM_RNA_PURITY_DEMO_ID
    assert analyze["validated_example_abstention_reason"] is None
    verify = operations[("POST", f"{prefix}/verify")]
    assert verify["request_max_bytes"] == GBM_RNA_PURITY_REPLAY_MAX_BYTES
    assert verify["result_max_bytes"] == GBM_RNA_PURITY_RESULT_MAX_BYTES
    assert verify["mutability_class"] == "verification"
    assert verify["validated_example_status"] == "abstained"
    assert verify["validated_example_id"] is None
    assert verify["validated_example_abstention_reason"] == "requires_prior_operation_result"
    for suffix in ("profile", "demo"):
        operation = operations[("GET", f"{prefix}/{suffix}")]
        assert operation["request_max_bytes"] is None
        assert operation["result_max_bytes"] == GBM_RNA_PURITY_RESULT_MAX_BYTES
        assert operation["validated_example_status"] == "abstained"
        assert operation["validated_example_id"] is None
        assert operation["validated_example_abstention_reason"] == "operation_has_no_request_body"


def _assert_longitudinal_metadata(
    operations: dict[tuple[str, str], dict[str, object]],
) -> None:
    analyze = operations[("POST", "/v1/research/longitudinal-gbm/analyze")]
    assert analyze["request_max_bytes"] == LONGITUDINAL_GBM_REQUEST_MAX_BYTES
    assert analyze["result_max_bytes"] == LONGITUDINAL_GBM_RESULT_MAX_BYTES
    assert analyze["safety_class"] == "research-use-only"
    assert analyze["mutability_class"] == "stateless-compute"
    assert analyze["validated_example_status"] == "validated"
    assert analyze["validated_example_id"] == LONGITUDINAL_DEMO_ID
    assert analyze["validated_example_abstention_reason"] is None
    verify = operations[("POST", "/v1/research/longitudinal-gbm/verify")]
    assert verify["request_max_bytes"] == LONGITUDINAL_GBM_REPLAY_MAX_BYTES
    assert verify["result_max_bytes"] == LONGITUDINAL_GBM_RESULT_MAX_BYTES
    assert verify["validated_example_status"] == "abstained"
    assert verify["validated_example_abstention_reason"] == "requires_prior_operation_result"
    profile = operations[("GET", "/v1/research/longitudinal-gbm/profile")]
    demo = operations[("GET", "/v1/research/longitudinal-gbm/demo")]
    assert profile["request_max_bytes"] is None
    assert demo["request_max_bytes"] is None
    assert profile["result_max_bytes"] == LONGITUDINAL_GBM_RESULT_MAX_BYTES
    assert demo["result_max_bytes"] == LONGITUDINAL_GBM_RESULT_MAX_BYTES


def _assert_longitudinal_phospho_metadata(
    operations: dict[tuple[str, str], dict[str, object]],
) -> None:
    prefix = "/v1/research/longitudinal-gbm-phospho"
    analyze = operations[("POST", f"{prefix}/analyze")]
    assert analyze["request_max_bytes"] == LONGITUDINAL_GBM_PHOSPHO_REQUEST_MAX_BYTES
    assert analyze["result_max_bytes"] == LONGITUDINAL_GBM_PHOSPHO_RESULT_MAX_BYTES
    assert analyze["safety_class"] == "research-use-only"
    assert analyze["mutability_class"] == "stateless-compute"
    assert analyze["validated_example_status"] == "validated"
    assert analyze["validated_example_id"] == LONGITUDINAL_PHOSPHO_DEMO_ID
    assert analyze["validated_example_abstention_reason"] is None
    verify = operations[("POST", f"{prefix}/verify")]
    assert verify["request_max_bytes"] == LONGITUDINAL_GBM_PHOSPHO_REPLAY_MAX_BYTES
    assert verify["result_max_bytes"] == LONGITUDINAL_GBM_PHOSPHO_RESULT_MAX_BYTES
    assert verify["validated_example_status"] == "abstained"
    assert verify["validated_example_abstention_reason"] == "requires_prior_operation_result"
    profile = operations[("GET", f"{prefix}/profile")]
    demo = operations[("GET", f"{prefix}/demo")]
    assert profile["request_max_bytes"] is None
    assert demo["request_max_bytes"] is None
    assert profile["result_max_bytes"] == LONGITUDINAL_GBM_PHOSPHO_RESULT_MAX_BYTES
    assert demo["result_max_bytes"] == LONGITUDINAL_GBM_PHOSPHO_RESULT_MAX_BYTES


def _assert_longitudinal_kinase_transition_metadata(
    operations: dict[tuple[str, str], dict[str, object]],
) -> None:
    prefix = "/v1/research/longitudinal-gbm-kinase-transition"
    analyze = operations[("POST", f"{prefix}/analyze")]
    assert analyze["request_max_bytes"] == LONGITUDINAL_GBM_KINASE_TRANSITION_REQUEST_MAX_BYTES
    assert analyze["result_max_bytes"] == LONGITUDINAL_GBM_KINASE_TRANSITION_RESULT_MAX_BYTES
    assert analyze["safety_class"] == "research-use-only"
    assert analyze["mutability_class"] == "stateless-compute"
    assert analyze["validated_example_status"] == "validated"
    assert analyze["validated_example_id"] == LONGITUDINAL_KINASE_TRANSITION_DEMO_ID
    assert analyze["validated_example_abstention_reason"] is None
    verify = operations[("POST", f"{prefix}/verify")]
    assert verify["request_max_bytes"] == LONGITUDINAL_GBM_KINASE_TRANSITION_REPLAY_MAX_BYTES
    assert verify["result_max_bytes"] == LONGITUDINAL_GBM_KINASE_TRANSITION_RESULT_MAX_BYTES
    assert verify["validated_example_status"] == "abstained"
    assert verify["validated_example_abstention_reason"] == "requires_prior_operation_result"
    profile = operations[("GET", f"{prefix}/profile")]
    demo = operations[("GET", f"{prefix}/demo")]
    assert profile["request_max_bytes"] is None
    assert demo["request_max_bytes"] is None
    assert profile["result_max_bytes"] == LONGITUDINAL_GBM_KINASE_TRANSITION_RESULT_MAX_BYTES
    assert demo["result_max_bytes"] == LONGITUDINAL_GBM_KINASE_TRANSITION_RESULT_MAX_BYTES


def _assert_longitudinal_neftel_transition_metadata(
    operations: dict[tuple[str, str], dict[str, object]],
) -> None:
    prefix = "/v1/research/longitudinal-gbm-neftel-transition"
    analyze = operations[("POST", f"{prefix}/analyze")]
    assert analyze["request_max_bytes"] == LONGITUDINAL_GBM_NEFTEL_TRANSITION_REQUEST_MAX_BYTES
    assert analyze["result_max_bytes"] == LONGITUDINAL_GBM_NEFTEL_TRANSITION_RESULT_MAX_BYTES
    assert analyze["safety_class"] == "research-use-only"
    assert analyze["mutability_class"] == "stateless-compute"
    assert analyze["validated_example_status"] == "validated"
    assert analyze["validated_example_id"] == LONGITUDINAL_NEFTEL_TRANSITION_DEMO_ID
    assert analyze["validated_example_abstention_reason"] is None
    verify = operations[("POST", f"{prefix}/verify")]
    assert verify["request_max_bytes"] == LONGITUDINAL_GBM_NEFTEL_TRANSITION_REPLAY_MAX_BYTES
    assert verify["result_max_bytes"] == LONGITUDINAL_GBM_NEFTEL_TRANSITION_RESULT_MAX_BYTES
    assert verify["validated_example_status"] == "abstained"
    assert verify["validated_example_abstention_reason"] == "requires_prior_operation_result"
    for suffix in ("profile", "demo"):
        operation = operations[("GET", f"{prefix}/{suffix}")]
        assert operation["request_max_bytes"] is None
        assert operation["result_max_bytes"] == LONGITUDINAL_GBM_NEFTEL_TRANSITION_RESULT_MAX_BYTES


def _assert_longitudinal_reactome_transition_metadata(
    operations: dict[tuple[str, str], dict[str, object]],
) -> None:
    prefix = "/v1/research/longitudinal-gbm-reactome-transition"
    analyze = operations[("POST", f"{prefix}/analyze")]
    assert analyze["request_max_bytes"] == LONGITUDINAL_GBM_REACTOME_TRANSITION_REQUEST_MAX_BYTES
    assert analyze["result_max_bytes"] == LONGITUDINAL_GBM_REACTOME_TRANSITION_RESULT_MAX_BYTES
    assert analyze["safety_class"] == "research-use-only"
    assert analyze["mutability_class"] == "stateless-compute"
    assert analyze["validated_example_status"] == "validated"
    assert analyze["validated_example_id"] == LONGITUDINAL_REACTOME_TRANSITION_DEMO_ID
    assert analyze["validated_example_abstention_reason"] is None
    verify = operations[("POST", f"{prefix}/verify")]
    assert verify["request_max_bytes"] == LONGITUDINAL_GBM_REACTOME_TRANSITION_REPLAY_MAX_BYTES
    assert verify["result_max_bytes"] == LONGITUDINAL_GBM_REACTOME_TRANSITION_RESULT_MAX_BYTES
    assert verify["validated_example_status"] == "abstained"
    assert verify["validated_example_abstention_reason"] == "requires_prior_operation_result"
    for suffix in ("profile", "demo"):
        operation = operations[("GET", f"{prefix}/{suffix}")]
        assert operation["request_max_bytes"] is None
        assert (
            operation["result_max_bytes"] == LONGITUDINAL_GBM_REACTOME_TRANSITION_RESULT_MAX_BYTES
        )


def _assert_longitudinal_complex_transition_metadata(
    operations: dict[tuple[str, str], dict[str, object]],
) -> None:
    prefix = "/v1/research/longitudinal-gbm-complex-transition"
    analyze = operations[("POST", f"{prefix}/analyze")]
    assert analyze["request_max_bytes"] == LONGITUDINAL_GBM_COMPLEX_TRANSITION_REQUEST_MAX_BYTES
    assert analyze["result_max_bytes"] == LONGITUDINAL_GBM_COMPLEX_TRANSITION_RESULT_MAX_BYTES
    assert analyze["safety_class"] == "research-use-only"
    assert analyze["mutability_class"] == "stateless-compute"
    assert analyze["validated_example_status"] == "validated"
    assert analyze["validated_example_id"] == LONGITUDINAL_COMPLEX_TRANSITION_DEMO_ID
    assert analyze["validated_example_abstention_reason"] is None
    verify = operations[("POST", f"{prefix}/verify")]
    assert verify["request_max_bytes"] == LONGITUDINAL_GBM_COMPLEX_TRANSITION_REPLAY_MAX_BYTES
    assert verify["result_max_bytes"] == LONGITUDINAL_GBM_COMPLEX_TRANSITION_RESULT_MAX_BYTES
    assert verify["mutability_class"] == "verification"
    assert verify["validated_example_status"] == "abstained"
    assert verify["validated_example_id"] is None
    assert verify["validated_example_abstention_reason"] == "requires_prior_operation_result"
    for suffix in ("profile", "demo"):
        operation = operations[("GET", f"{prefix}/{suffix}")]
        assert operation["request_max_bytes"] is None
        assert operation["result_max_bytes"] == LONGITUDINAL_GBM_COMPLEX_TRANSITION_RESULT_MAX_BYTES
        assert operation["validated_example_status"] == "abstained"
        assert operation["validated_example_id"] is None
        assert operation["validated_example_abstention_reason"] == ("operation_has_no_request_body")


def _assert_factor_graph_metadata(
    operations: dict[tuple[str, str], dict[str, object]],
) -> None:
    prefix = "/v1/research/gbm-factor-graph"
    analyze = operations[("POST", f"{prefix}/analyze")]
    assert analyze["request_max_bytes"] == GBM_FACTOR_GRAPH_REQUEST_MAX_BYTES
    assert analyze["result_max_bytes"] == GBM_FACTOR_GRAPH_RESULT_MAX_BYTES
    assert analyze["safety_class"] == "research-use-only"
    assert analyze["mutability_class"] == "stateless-compute"
    assert analyze["validated_example_status"] == "validated"
    assert analyze["validated_example_id"] == FACTOR_GRAPH_DEMO_ID
    assert analyze["validated_example_abstention_reason"] is None
    verify = operations[("POST", f"{prefix}/verify")]
    assert verify["request_max_bytes"] == GBM_FACTOR_GRAPH_REPLAY_MAX_BYTES
    assert verify["result_max_bytes"] == GBM_FACTOR_GRAPH_RESULT_MAX_BYTES
    assert verify["mutability_class"] == "verification"
    assert verify["validated_example_status"] == "abstained"
    assert verify["validated_example_id"] is None
    assert verify["validated_example_abstention_reason"] == "requires_prior_operation_result"
    for suffix in ("profile", "demo"):
        operation = operations[("GET", f"{prefix}/{suffix}")]
        assert operation["request_max_bytes"] is None
        assert operation["result_max_bytes"] == GBM_FACTOR_GRAPH_RESULT_MAX_BYTES
        assert operation["validated_example_status"] == "abstained"
        assert operation["validated_example_id"] is None
        assert operation["validated_example_abstention_reason"] == "operation_has_no_request_body"


def _assert_m09_facade_metadata(
    operations: dict[tuple[str, str], dict[str, object]],
) -> None:
    prefix = M09_COMPLEX_TRANSITION_ROUTE_PREFIX
    analyze = operations[("POST", f"{prefix}/analyze")]
    assert analyze["request_max_bytes"] == M09_COMPLEX_TRANSITION_REQUEST_MAX_BYTES
    assert analyze["result_max_bytes"] == M09_COMPLEX_TRANSITION_RESULT_MAX_BYTES
    assert analyze["safety_class"] == "research-use-only"
    assert analyze["mutability_class"] == "stateless-compute"
    assert analyze["validated_example_status"] == "validated"
    assert analyze["validated_example_id"] == LONGITUDINAL_COMPLEX_TRANSITION_DEMO_ID
    assert analyze["validated_example_abstention_reason"] is None
    verify = operations[("POST", f"{prefix}/verify")]
    assert verify["request_max_bytes"] == M09_COMPLEX_TRANSITION_REPLAY_MAX_BYTES
    assert verify["result_max_bytes"] == M09_COMPLEX_TRANSITION_RESULT_MAX_BYTES
    assert verify["mutability_class"] == "verification"
    assert verify["validated_example_status"] == "abstained"
    assert verify["validated_example_abstention_reason"] == "requires_prior_operation_result"
    for suffix in ("profile", "demo"):
        operation = operations[("GET", f"{prefix}/{suffix}")]
        assert operation["request_max_bytes"] is None
        assert operation["result_max_bytes"] == M09_COMPLEX_TRANSITION_RESULT_MAX_BYTES


def _assert_m11_facade_metadata(
    operations: dict[tuple[str, str], dict[str, object]],
) -> None:
    prefix = "/v2/research/modules/m11/protein-native-subtype"
    analyze = operations[("POST", f"{prefix}/analyze")]
    assert analyze["request_max_bytes"] == M11_PROTEIN_NATIVE_SUBTYPE_REQUEST_MAX_BYTES
    assert analyze["result_max_bytes"] == M11_PROTEIN_NATIVE_SUBTYPE_RESULT_MAX_BYTES
    assert analyze["safety_class"] == "research-use-only"
    assert analyze["mutability_class"] == "stateless-compute"
    assert analyze["validated_example_status"] == "validated"
    assert analyze["validated_example_id"] == GBM_DEMO_ID
    verify = operations[("POST", f"{prefix}/verify")]
    assert verify["request_max_bytes"] == M11_PROTEIN_NATIVE_SUBTYPE_REPLAY_MAX_BYTES
    assert verify["result_max_bytes"] == M11_PROTEIN_NATIVE_SUBTYPE_RESULT_MAX_BYTES
    assert verify["mutability_class"] == "verification"
    for suffix in ("profile", "demo"):
        operation = operations[("GET", f"{prefix}/{suffix}")]
        assert operation["request_max_bytes"] is None
        assert operation["result_max_bytes"] == M11_PROTEIN_NATIVE_SUBTYPE_RESULT_MAX_BYTES


def _assert_m10_facade_metadata(
    operations: dict[tuple[str, str], dict[str, object]],
) -> None:
    prefix = "/v2/research/modules/m10/functional-proteotype"
    analyze = operations[("POST", f"{prefix}/analyze")]
    assert analyze["request_max_bytes"] == M10_FUNCTIONAL_PROTEOTYPE_REQUEST_MAX_BYTES
    assert analyze["result_max_bytes"] == M10_FUNCTIONAL_PROTEOTYPE_RESULT_MAX_BYTES
    assert analyze["safety_class"] == "research-use-only"
    assert analyze["mutability_class"] == "stateless-compute"
    assert analyze["validated_example_status"] == "validated"
    assert analyze["validated_example_id"] == FUNCTIONAL_PROTEOTYPE_DEMO_ID
    verify = operations[("POST", f"{prefix}/verify")]
    assert verify["request_max_bytes"] == M10_FUNCTIONAL_PROTEOTYPE_REPLAY_MAX_BYTES
    assert verify["result_max_bytes"] == M10_FUNCTIONAL_PROTEOTYPE_RESULT_MAX_BYTES
    assert verify["mutability_class"] == "verification"
    for suffix in ("profile", "demo"):
        operation = operations[("GET", f"{prefix}/{suffix}")]
        assert operation["request_max_bytes"] is None
        assert operation["result_max_bytes"] == M10_FUNCTIONAL_PROTEOTYPE_RESULT_MAX_BYTES


def _assert_m14_facade_metadata(
    operations: dict[tuple[str, str], dict[str, object]],
) -> None:
    prefix = "/v2/research/modules/m14/microenvironment-protein-programs"
    analyze = operations[("POST", f"{prefix}/analyze")]
    assert analyze["request_max_bytes"] == M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_REQUEST_MAX_BYTES
    assert analyze["result_max_bytes"] == M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_RESULT_MAX_BYTES
    assert analyze["safety_class"] == "research-use-only"
    assert analyze["mutability_class"] == "stateless-compute"
    assert analyze["validated_example_status"] == "validated"
    assert analyze["validated_example_id"] == M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_DEMO_ID
    verify = operations[("POST", f"{prefix}/verify")]
    assert verify["request_max_bytes"] == M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_REPLAY_MAX_BYTES
    assert verify["result_max_bytes"] == M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_RESULT_MAX_BYTES
    assert verify["mutability_class"] == "verification"
    for suffix in ("profile", "demo"):
        operation = operations[("GET", f"{prefix}/{suffix}")]
        assert operation["request_max_bytes"] is None
        assert (
            operation["result_max_bytes"] == M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_RESULT_MAX_BYTES
        )


def _assert_m15_facade_metadata(
    operations: dict[tuple[str, str], dict[str, object]],
) -> None:
    prefix = M15_LONGITUDINAL_RECURRENCE_ROUTE_PREFIX
    analyze = operations[("POST", f"{prefix}/analyze")]
    assert analyze["request_max_bytes"] == LONGITUDINAL_GBM_REQUEST_MAX_BYTES
    assert analyze["result_max_bytes"] == LONGITUDINAL_GBM_RESULT_MAX_BYTES
    assert analyze["safety_class"] == "research-use-only"
    assert analyze["mutability_class"] == "stateless-compute"
    assert analyze["validated_example_status"] == "validated"
    assert analyze["validated_example_id"] == LONGITUDINAL_DEMO_ID
    verify = operations[("POST", f"{prefix}/verify")]
    assert verify["request_max_bytes"] == LONGITUDINAL_GBM_REPLAY_MAX_BYTES
    assert verify["result_max_bytes"] == LONGITUDINAL_GBM_RESULT_MAX_BYTES
    assert verify["mutability_class"] == "verification"
    for suffix in ("profile", "demo"):
        operation = operations[("GET", f"{prefix}/{suffix}")]
        assert operation["request_max_bytes"] is None
        assert operation["result_max_bytes"] == LONGITUDINAL_GBM_RESULT_MAX_BYTES


def _assert_governed_metadata(operations: dict[tuple[str, str], dict[str, object]]) -> None:
    governed = operations[("POST", "/v1/modules/M01-01/protocols")]
    assert governed["request_max_bytes"] == _APPLICATION_DEFAULT_REQUEST_MAX_BYTES
    assert governed["safety_class"] == "S2"
    assert governed["validated_example_status"] == "abstained"
    assert governed["validated_example_id"] is None
    assert governed["validated_example_abstention_reason"] == "no_repository_validated_fixture"
    assert (
        operations[("POST", "/v1/modules/M19-01/verify")]["request_max_bytes"]
        == _M1901_RESULT_MAX_BYTES
    )
    inspect = operations[("POST", "/v1/modules/M01-03/inspect")]
    assert inspect["request_media_types"] == ["application/octet-stream"]
    assert inspect["request_max_bytes"] == _APPLICATION_DEFAULT_REQUEST_MAX_BYTES
    assert operations[("GET", "/v1/m19-05/schema/{name}")]["safety_class"] == "S2"
    assert operations[("POST", "/v1/modules/M27-02/lineage")]["safety_class"] == "S3"


def _assert_operational_surface(operations: dict[tuple[str, str], dict[str, object]]) -> None:
    assert ("GET", "/livez") in operations
    assert operations[("GET", "/livez")]["safety_class"] == "operational"
    assert ("GET", "/readyz") in operations
    assert ("GET", "/healthz") in operations
    assert any(path.startswith("/m26-02/") for _method, path in operations)


def _assert_tamper_is_rejected(app: FastAPI, payload: dict[str, object]) -> None:
    tampered = deepcopy(payload)
    catalog_operations = cast("list[dict[str, object]]", tampered["operations"])
    profile_entry = next(
        operation
        for operation in catalog_operations
        if operation["method"] == "GET"
        and operation["path"] == "/v1/research/proteogenomic-state/profile"
    )
    profile_entry["validated_example_abstention_reason"] = None
    with pytest.raises(
        OperationCatalogValidationError,
        match="validated_example_abstention_reason is None",
    ):
        validate_operation_catalog(app, tampered)


def test_v2_catalog_discovers_research_and_unlimited_governed_operations(tmp_path: Path) -> None:
    app = create_deployment_app(
        DeploymentSettings(database_path=tmp_path / "events.sqlite3", environment="test")
    )

    with TestClient(app) as client:
        first = client.get("/v2/deployment/catalog")
        second = client.get("/v2/deployment/catalog")
        legacy = client.get("/v1/deployment/catalog")
        oversized_default = client.post(
            "/v1/modules/M01-01/protocols",
            content=b"{}",
            headers={
                "content-type": "application/json",
                "content-length": str(_APPLICATION_DEFAULT_REQUEST_MAX_BYTES + 1),
            },
        )
        replay_above_result_below_request = client.post(
            "/v1/research/longitudinal-gbm/verify",
            content=b"{}",
            headers={
                "content-type": "application/json",
                "content-length": str(LONGITUDINAL_GBM_RESULT_MAX_BYTES + 1),
            },
        )

    assert first.status_code == _HTTP_OK
    assert second.json() == first.json()
    payload = first.json()
    assert payload["catalog_version"] == _CATALOG_VERSION
    assert payload["catalog_digest"].startswith("sha256:")
    assert payload["operation_count"] == len(payload["operations"])
    report = validate_operation_catalog(app, payload)
    _assert_exhaustive_report(report, payload["catalog_digest"])

    operations = {
        (operation["method"], operation["path"]): operation for operation in payload["operations"]
    }
    assert len(operations) == payload["operation_count"]
    _assert_research_metadata(operations)
    _assert_governed_metadata(operations)
    _assert_operational_surface(operations)

    assert legacy.status_code == _HTTP_OK
    assert legacy.json()["catalog_version"] == 1
    assert legacy.json()["catalog_digest"] == _V1_COMPATIBILITY_CATALOG_DIGEST
    assert "operations" not in legacy.json()
    assert oversized_default.status_code == _HTTP_PAYLOAD_TOO_LARGE
    assert oversized_default.json() == {"detail": "request body exceeds the byte limit"}
    assert replay_above_result_below_request.status_code == _HTTP_UNPROCESSABLE
    _assert_tamper_is_rejected(app, payload)


def test_catalog_ignores_non_http_methods_and_malformed_parameter_metadata(
    tmp_path: Path,
) -> None:
    app = FastAPI()
    app.add_middleware(GZipMiddleware)

    @app.get("/probe")
    def probe() -> dict[str, bool]:
        return {"ok": True}

    route = next(item for item in app.routes if getattr(item, "path", None) == "/probe")
    assert isinstance(route, APIRoute)
    assert route.methods is not None
    route.methods.add("CONNECT")
    app.openapi = lambda: {  # type: ignore[method-assign]
        "paths": {
            "/probe": {
                "get": {
                    "parameters": [None, {"in": 7}, {"in": "query"}],
                    "responses": {},
                }
            }
        }
    }
    catalog = _operation_catalog(
        app,
        DeploymentSettings(database_path=tmp_path / "events.sqlite3", environment="test"),
    )

    operations = catalog["operations"]
    assert isinstance(operations, list)
    assert len(operations) == 1
    assert operations[0]["method"] == "GET"
    assert operations[0]["parameter_locations"] == ["query"]


def test_catalog_rejects_duplicate_method_path_registrations(tmp_path: Path) -> None:
    app = FastAPI()

    @app.get("/duplicate")
    def first() -> dict[str, int]:
        return {"handler": 1}

    @app.get("/duplicate")
    def second() -> dict[str, int]:
        return {"handler": 2}

    with pytest.raises(
        DeploymentConfigurationError,
        match=r"duplicate mounted method/path registrations: GET /duplicate",
    ):
        _operation_catalog(
            app,
            DeploymentSettings(database_path=tmp_path / "events.sqlite3", environment="test"),
        )


def test_repository_validation_executes_every_typed_demo_identity(tmp_path: Path) -> None:
    report = run_repository_validation(tmp_path / "catalog-validation.sqlite3")

    assert report["executed_validated_example_ids"] == [
        DEMO_ID,
        FUNCTIONAL_PROTEOTYPE_DEMO_ID,
        GBM_DEMO_ID,
        NEFTEL_DEMO_ID,
        MASTER_KINASE_DEMO_ID,
        GBM_RNA_PURITY_DEMO_ID,
        LONGITUDINAL_DEMO_ID,
        LONGITUDINAL_PHOSPHO_DEMO_ID,
        LONGITUDINAL_KINASE_TRANSITION_DEMO_ID,
        LONGITUDINAL_NEFTEL_TRANSITION_DEMO_ID,
        LONGITUDINAL_REACTOME_TRANSITION_DEMO_ID,
        LONGITUDINAL_COMPLEX_TRANSITION_DEMO_ID,
        FACTOR_GRAPH_DEMO_ID,
        LONGITUDINAL_COMPLEX_TRANSITION_DEMO_ID,
        FUNCTIONAL_PROTEOTYPE_DEMO_ID,
        GBM_DEMO_ID,
        M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_DEMO_ID,
        LONGITUDINAL_DEMO_ID,
    ]
