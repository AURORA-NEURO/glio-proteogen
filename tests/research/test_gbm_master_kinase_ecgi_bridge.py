"""Tests for the explicit GBM master-kinase → ECGI handoff."""

from __future__ import annotations

import pytest

from glio_proteogen.research.gbm_master_kinases import (
    ECGI_EXTERNAL_PROFILE_ID,
    ECGI_EXTERNAL_RANK_PROFILE_ID,
    MasterKinaseRequest,
    PhosphositeEvidenceState,
    PhosphositeObservation,
    StandardizedContrastReference,
    analyze_master_kinases,
    build_ecgi_external_kinase_profile,
    synthetic_demo_request,
)
from glio_proteogen.research.gbm_master_kinases.canonical import sha256_digest
from glio_proteogen.research.proteogenomic_state import (
    EdgeKind,
    EvidenceModality,
    EvidenceObservation,
    EvidenceState,
    GraphEdge,
    GraphNode,
    NodeKind,
    ProteogenomicStateRequest,
    analyze_proteogenomic_state,
)

PROVENANCE = sha256_digest({"test": "gbm-master-kinase-ecgi-bridge"})


@pytest.fixture(scope="module")
def demo_result():
    request = synthetic_demo_request().model_copy(
        update={"bootstrap_replicates": 16, "permutation_replicates": 64}
    )
    return analyze_master_kinases(request)


def test_bridge_requires_explicit_mapping_and_binds_result_digest(demo_result) -> None:
    profile = build_ecgi_external_kinase_profile(
        demo_result,
        node_id_by_kinase_id={
            "PRKCD": "kinase.prkcd",
            "PHKG2": "kinase.phkg2",
        },
    )
    assert profile.profile_id == ECGI_EXTERNAL_PROFILE_ID
    assert profile.source_digest == demo_result.result_digest
    assert tuple(item.kinase_id for item in profile.estimates) == (
        "kinase.phkg2",
        "kinase.prkcd",
    )
    phkg2 = next(item for item in profile.estimates if item.kinase_id == "kinase.phkg2")
    source = next(item for item in demo_result.kinase_evidence if item.kinase_id == "PHKG2")
    assert phkg2.activity == source.location.score
    assert phkg2.lower_bound == source.location.lower_bound
    assert phkg2.upper_bound == source.location.upper_bound


def test_bridge_can_export_independent_rank_enrichment_profile(demo_result) -> None:
    profile = build_ecgi_external_kinase_profile(
        demo_result,
        node_id_by_kinase_id={"PRKCD": "kinase.prkcd", "PHKG2": "kinase.phkg2"},
        method="rank_enrichment",
    )
    assert profile.profile_id == ECGI_EXTERNAL_RANK_PROFILE_ID
    assert profile.source_digest == demo_result.result_digest
    phkg2 = next(item for item in profile.estimates if item.kinase_id == "kinase.phkg2")
    source = next(item for item in demo_result.kinase_evidence if item.kinase_id == "PHKG2")
    assert phkg2.activity == source.rank_enrichment.score
    assert phkg2.lower_bound == source.rank_enrichment.lower_bound
    assert phkg2.upper_bound == source.rank_enrichment.upper_bound


def test_bridge_rejects_unknown_method(demo_result) -> None:
    with pytest.raises(ValueError, match="method must be 'location' or 'rank_enrichment'"):
        build_ecgi_external_kinase_profile(
            demo_result,
            node_id_by_kinase_id={"PRKCD": "kinase.prkcd"},
            method="unknown",  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("mapping", "message"),
    [
        ({}, "explicit kinase-to-ECGI node mapping is required"),
        ({"NOT_A_KINASE": "kinase.unknown"}, "unknown master kinases"),
        ({"PRKCD": "kinase.same", "PHKG2": "kinase.same"}, "at most one"),
    ],
)
def test_bridge_rejects_ambiguous_mappings(demo_result, mapping, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        build_ecgi_external_kinase_profile(
            demo_result,
            node_id_by_kinase_id=mapping,
        )


@pytest.mark.parametrize(
    ("method", "message"),
    [
        ("location", "no supported master-kinase estimates"),
        ("rank_enrichment", "no supported master-kinase rank_enrichment estimates"),
    ],
)
def test_bridge_rejects_all_abstained_estimates(method: str, message: str) -> None:
    request = MasterKinaseRequest(
        sample_id="bridge.abstained",
        observations=(
            PhosphositeObservation(
                observation_id="bridge.unsupported",
                phosphosite_id="FAKE-S1s",
                state=PhosphositeEvidenceState.UNSUPPORTED,
                quality_weight=0.0,
                provenance_digest=PROVENANCE,
            ),
        ),
        bootstrap_replicates=16,
        permutation_replicates=64,
        contrast_reference=StandardizedContrastReference(
            contrast_id="bridge.contrast",
            numerator_label="case",
            denominator_label="reference",
        ),
    )
    result = analyze_master_kinases(request)
    with pytest.raises(ValueError, match=message):
        build_ecgi_external_kinase_profile(
            result,
            node_id_by_kinase_id={"PRKCD": "kinase.prkcd"},
            method=method,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("missing_bound", ["score", "lower_bound", "upper_bound"])
def test_bridge_skips_incomplete_supported_intervals(demo_result, missing_bound: str) -> None:
    source = next(item for item in demo_result.kinase_evidence if item.kinase_id == "PRKCD")
    malformed_location = source.location.model_copy(update={missing_bound: None})
    malformed_evidence = source.model_copy(update={"location": malformed_location})
    evidence = tuple(
        malformed_evidence if item.kinase_id == "PRKCD" else item
        for item in demo_result.kinase_evidence
    )
    malformed_result = demo_result.model_copy(update={"kinase_evidence": evidence})
    with pytest.raises(ValueError, match="no supported master-kinase estimates"):
        build_ecgi_external_kinase_profile(
            malformed_result,
            node_id_by_kinase_id={"PRKCD": "kinase.prkcd"},
        )


@pytest.mark.parametrize(
    ("method", "profile_id"),
    [
        ("location", ECGI_EXTERNAL_PROFILE_ID),
        ("rank_enrichment", ECGI_EXTERNAL_RANK_PROFILE_ID),
    ],
)
def test_bridge_is_consumed_by_ecgi_as_comparison_only(
    demo_result,
    method: str,
    profile_id: str,
) -> None:
    profile = build_ecgi_external_kinase_profile(
        demo_result,
        node_id_by_kinase_id={"PRKCD": "kinase.prkcd", "PHKG2": "kinase.phkg2"},
        method=method,  # type: ignore[arg-type]
    )
    nodes = (
        GraphNode(node_id="kinase.prkcd", kind=NodeKind.KINASE),
        GraphNode(node_id="kinase.phkg2", kind=NodeKind.KINASE),
        *(GraphNode(node_id=f"site.{index}", kind=NodeKind.PHOSPHOSITE) for index in range(3)),
        *(
            GraphNode(node_id=f"background.{index}", kind=NodeKind.PHOSPHOSITE)
            for index in range(30)
        ),
    )
    edges = tuple(
        GraphEdge(
            edge_id=f"edge.{kinase}.{index}",
            source_id=f"kinase.{kinase}",
            target_id=f"site.{index}",
            kind=EdgeKind.KINASE_SUBSTRATE,
            sign=1,
            weight=1.0,
        )
        for kinase in ("prkcd", "phkg2")
        for index in range(3)
    )
    observations = (
        *tuple(
            EvidenceObservation(
                observation_id=f"observation.site.{index}",
                node_id=f"site.{index}",
                modality=EvidenceModality.PHOSPHOPROTEOMICS,
                state=EvidenceState.OBSERVED,
                standardized_effect=0.8,
                standard_error=0.2,
                quality_weight=1.0,
                provenance_digest=PROVENANCE,
            )
            for index in range(3)
        ),
        *tuple(
            EvidenceObservation(
                observation_id=f"observation.background.{index}",
                node_id=f"background.{index}",
                modality=EvidenceModality.PHOSPHOPROTEOMICS,
                state=EvidenceState.OBSERVED,
                standardized_effect=-0.8,
                standard_error=0.2,
                quality_weight=1.0,
                provenance_digest=PROVENANCE,
            )
            for index in range(30)
        ),
        *tuple(
            EvidenceObservation(
                observation_id=f"observation.kinase.{kinase}",
                node_id=f"kinase.{kinase}",
                modality=EvidenceModality.PHOSPHOPROTEOMICS,
                state=EvidenceState.OBSERVED,
                standardized_effect=0.8,
                standard_error=0.2,
                quality_weight=1.0,
                provenance_digest=PROVENANCE,
            )
            for kinase in ("prkcd", "phkg2")
        ),
    )
    request = ProteogenomicStateRequest(
        sample_id="bridge.ecgi",
        nodes=nodes,
        edges=edges,
        observations=observations,
        bootstrap_replicates=8,
        permutation_replicates=32,
        external_kinase_profile=profile,
    )
    result = analyze_proteogenomic_state(request)
    comparison = result.external_kinase_comparison
    assert comparison is not None
    assert comparison.profile_id == profile_id
    assert comparison.source_digest == demo_result.result_digest
    assert {item.kinase_id for item in comparison.matches} == {
        "kinase.prkcd",
        "kinase.phkg2",
    }
    assert comparison.note == (
        "External values are compared by exact identifier and never merged or substituted."
    )
