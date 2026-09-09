"""Scientific and replay checks for the Neftel-to-ECGI GBM bridge."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from glio_proteogen.research.gbm_microenvironment_graph import (
    MicroenvironmentGraphReplayRequest,
    MicroenvironmentGraphRequest,
    analyze_microenvironment_graph,
    microenvironment_graph_profile,
    synthetic_microenvironment_graph_request,
    verify_microenvironment_graph_replay,
)
from glio_proteogen.research.neftel_protein_programs import synthetic_demo_request
from glio_proteogen.research.proteogenomic_state import EvidenceState


def test_profile_binds_both_child_engines() -> None:
    profile = microenvironment_graph_profile()
    assert profile.source_profile_digest.startswith("sha256:")
    assert profile.graph_profile_digest.startswith("sha256:")
    assert profile.supported_source_families == (
        "mesenchymal_like",
        "oligodendrocyte_progenitor_like",
    )
    assert profile.missing_families_are_not_negative is True
    assert profile.cell_fraction_claim_permitted is False


def test_synthetic_bridge_projects_supported_mes_and_opc_evidence() -> None:
    request = synthetic_microenvironment_graph_request()
    result = analyze_microenvironment_graph(request)
    source_by_family = {
        str(item.program_id): item for item in result.source_result.program_evidence
    }
    assert source_by_family["mesenchymal_like"].location is not None
    assert source_by_family["oligodendrocyte_progenitor_like"].location is not None
    graph_by_node = {
        str(item.observation_id): item for item in result.graph_request.observations
    }
    assert (
        graph_by_node["observation.gbm_microenvironment.mesenchymal"].state
        is EvidenceState.OBSERVED
    )
    assert (
        graph_by_node["observation.gbm_microenvironment.opc_like"].state
        is EvidenceState.OBSERVED
    )
    node_by_id = {str(item.node_id): item for item in result.graph_result.node_states}
    assert (
        node_by_id["pathway.gbm_microenvironment.mesenchymal"].classification.value
        == "activated"
    )
    assert (
        node_by_id["pathway.gbm_microenvironment.opc_like"].classification.value
        == "suppressed"
    )


def test_missing_source_families_remain_missing() -> None:
    source = synthetic_demo_request()
    request = MicroenvironmentGraphRequest(sample_id=source.sample_id, source_request=source)
    result = analyze_microenvironment_graph(request)
    graph_by_node = {
        str(item.observation_id): item for item in result.graph_request.observations
    }
    assert (
        graph_by_node["observation.gbm_microenvironment.mesenchymal"].state
        is EvidenceState.MISSING
    )
    assert (
        graph_by_node["observation.gbm_microenvironment.opc_like"].state
        is EvidenceState.MISSING
    )
    assert graph_by_node["observation.gbm_microenvironment.mesenchymal"].standardized_effect is None


def test_replay_is_exact_and_sample_binding_is_strict() -> None:
    request = synthetic_microenvironment_graph_request()
    result = analyze_microenvironment_graph(request)
    replay = verify_microenvironment_graph_replay(
        MicroenvironmentGraphReplayRequest(request=request, result=result)
    )
    assert replay.verified is True
    with pytest.raises(ValidationError, match="sample_id must match"):
        MicroenvironmentGraphRequest(
            sample_id="different-sample", source_request=request.source_request
        )
