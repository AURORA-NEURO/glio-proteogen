"""Adversarial request, plugin, and replay boundaries for M27-02."""

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m27_02 import (
    ComplexActivityLineageResult,
    LineageEdge,
    LineageFinding,
    LineageFindingCode,
    LineageGraph,
    LineageNode,
    LineageNodeKind,
    LineageRelation,
    ReproducibilityBundle,
    ResolveComplexActivityLineageRequest,
    result_payload_digest,
)
from glio_proteogen.contracts.m27_02.canonical import graph_payload_digest
from glio_proteogen.kernel.models import EvidenceReference
from glio_proteogen.kernel.strict_json import StrictJsonError
from glio_proteogen.modules.c27_complex_activity.m27_02_lineage_service import (
    M2702LineageResolver,
    M2702Plugin,
    M2702Service,
    resolve_complex_activity_lineage,
)
from tests.runtime.test_m27_02_lineage import _request

_NODE_KIND_COUNT = 7
_RELATION_COUNT = 5
_FINDING_CODE_COUNT = 5


def test_request_rejects_non_m2701_upstream_media_type() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="M27-01 search result"):
        ResolveComplexActivityLineageRequest.model_validate(
            request.model_copy(
                update={
                    "upstream_result": request.upstream_result.model_copy(
                        update={"media_type": "application/json"}
                    )
                }
            ),
            strict=True,
        )


def test_plugin_rejects_duplicate_json_keys_before_validation() -> None:
    plugin = M2702Plugin(M2702Service())
    with pytest.raises(StrictJsonError):
        plugin.validate(b'{"request_id":"one","request_id":"two"}')


def test_resigned_graph_manifest_tamper_is_rejected() -> None:
    result = M2702LineageResolver().resolve(_request())
    assert result.lineage_graph is not None
    tampered_graph = result.lineage_graph.model_copy(
        update={
            "reproducibility_bundle": result.lineage_graph.reproducibility_bundle.model_copy(
                update={"manifest_digest": "sha256:" + "f" * 64}
            )
        }
    )
    payload = result.model_dump(mode="python")
    payload["lineage_graph"] = tampered_graph
    payload["result_digest"] = result_payload_digest(payload)

    with pytest.raises(ValidationError, match="does not bind graph content"):
        ComplexActivityLineageResult.model_validate(payload, strict=True)


def test_contract_enumerations_and_self_link_are_closed() -> None:
    assert len(tuple(LineageNodeKind)) == _NODE_KIND_COUNT
    assert len(tuple(LineageRelation)) == _RELATION_COUNT
    assert len(tuple(LineageFindingCode)) == _FINDING_CODE_COUNT
    request = _request()
    evidence = EvidenceReference(
        reference=request.source_artifacts[0],
        role="evidence",
        claim="synthetic adversarial evidence",
    )
    with pytest.raises(ValidationError, match="endpoints must be distinct"):
        LineageEdge(
            edge_id="edge.self",
            source_node_id="node.same",
            target_node_id="node.same",
            relation=LineageRelation.USES,
            producing_version="1.0.0",
            evidence=(evidence,),
        )


def test_bundle_and_graph_duplicate_references_are_rejected() -> None:
    request = _request()
    evidence = EvidenceReference(
        reference=request.source_artifacts[0],
        role="evidence",
        claim="synthetic adversarial evidence",
    )
    with pytest.raises(ValidationError, match="bundle node ids must be unique"):
        ReproducibilityBundle(
            bundle_id="bundle.duplicate-nodes",
            version="1.0.0",
            root_node_id="node.one",
            node_ids=("node.one", "node.one"),
            producing_versions=("1.0.0",),
            manifest_digest=request.source_artifacts[0].digest,
            evidence=(evidence,),
        )
    first = LineageNode(
        node_id="node.one",
        kind=LineageNodeKind.SOURCE_DATA,
        name="node.one",
        version="1.0.0",
        digest=request.source_artifacts[0].digest,
        media_type="application/json",
        evidence=(evidence,),
    )
    with pytest.raises(ValidationError, match="lineage node ids must be unique"):
        LineageGraph(
            graph_id="graph.duplicate-nodes",
            version="1.0.0",
            nodes=(first, first),
            reproducibility_bundle=ReproducibilityBundle(
                bundle_id="bundle.duplicate-graph",
                version="1.0.0",
                root_node_id=first.node_id,
                node_ids=(first.node_id,),
                producing_versions=("1.0.0",),
                manifest_digest=request.source_artifacts[0].digest,
                evidence=(evidence,),
            ),
            evidence=(evidence,),
        )


def test_request_requires_upstream_reference_and_result_finding_ids() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="included in source artifacts"):
        ResolveComplexActivityLineageRequest(
            request_id=request.request_id,
            context=request.context,
            upstream_result=request.upstream_result,
            root_object_id=request.root_object_id,
            source_artifacts=(request.source_artifacts[1],),
        )
    result = M2702LineageResolver().resolve(request)
    assert result.lineage_graph is not None
    finding = LineageFinding(
        finding_id="finding.duplicate",
        code=LineageFindingCode.BROKEN_LINK,
        message="synthetic duplicate finding",
    )
    payload = result.model_dump(mode="python")
    payload["findings"] = (finding, finding)
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValidationError, match="finding ids must be unique"):
        ComplexActivityLineageResult.model_validate(payload, strict=True)


def test_public_entrypoint_dict_replay_root_collision_and_descriptor() -> None:
    request = _request()
    resolver = M2702LineageResolver()
    assert resolver.resolve(request.model_dump(mode="python")) == resolver.resolve(request)
    assert resolve_complex_activity_lineage(request) == resolver.resolve(request)
    assert M2702Plugin(M2702Service()).descriptor().module_id == "GLIO-PROTEOGEN-M27-02"
    collided = request.model_copy(
        update={"root_object_id": request.source_artifacts[0].artifact_id}
    )
    assert resolver.resolve(collided).status.value == "abstained"
    assert graph_payload_digest({"reproducibility_bundle": "not-a-mapping"})


def test_graph_and_result_closure_reject_forged_references() -> None:
    request = _request()
    result = M2702LineageResolver().resolve(request)
    assert result.lineage_graph is not None
    graph = result.lineage_graph
    with pytest.raises(ValidationError, match="bundle edge ids must be unique"):
        ReproducibilityBundle(
            bundle_id="bundle.duplicate-edges",
            version="1.0.0",
            root_node_id=graph.nodes[0].node_id,
            node_ids=(graph.nodes[0].node_id,),
            edge_ids=("edge.one", "edge.one"),
            producing_versions=("1.0.0",),
            manifest_digest=request.source_artifacts[0].digest,
            evidence=(
                EvidenceReference(
                    reference=request.source_artifacts[0],
                    role="evidence",
                    claim="synthetic adversarial evidence",
                ),
            ),
        )
    with pytest.raises(ValidationError, match="bundle root must reference"):
        LineageGraph.model_validate(
            graph.model_copy(
                update={
                    "reproducibility_bundle": graph.reproducibility_bundle.model_copy(
                        update={
                            "root_node_id": "node.unknown",
                            "node_ids": (*graph.reproducibility_bundle.node_ids, "node.unknown"),
                        }
                    )
                }
            ),
            strict=True,
        )
    with pytest.raises(ValidationError, match="bundle references an unknown lineage node"):
        LineageGraph.model_validate(
            graph.model_copy(
                update={
                    "reproducibility_bundle": graph.reproducibility_bundle.model_copy(
                        update={
                            "node_ids": (*graph.reproducibility_bundle.node_ids, "node.unknown")
                        }
                    )
                }
            ),
            strict=True,
        )
    with pytest.raises(ValidationError, match="bundle references an unknown lineage edge"):
        LineageGraph.model_validate(
            graph.model_copy(
                update={
                    "reproducibility_bundle": graph.reproducibility_bundle.model_copy(
                        update={
                            "edge_ids": (*graph.reproducibility_bundle.edge_ids, "edge.unknown")
                        }
                    )
                }
            ),
            strict=True,
        )
    result_payload = result.model_dump(mode="python")
    result_payload["request_digest"] = request.source_artifacts[0].digest
    with pytest.raises(ValidationError, match="request digest"):
        ComplexActivityLineageResult.model_validate(result_payload, strict=True)
    result_payload = result.model_dump(mode="python")
    result_payload["lineage_graph"] = None
    with pytest.raises(ValidationError, match="resolved result requires"):
        ComplexActivityLineageResult.model_validate(result_payload, strict=True)
