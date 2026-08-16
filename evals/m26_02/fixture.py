"""Deterministic M26-02 request fixtures with explicit control boundaries."""

from __future__ import annotations

from datetime import UTC, datetime

from glio_proteogen.contracts.m26_02 import (
    M2602_UPSTREAM_MEDIA_TYPE,
    BuildProteinSubtypeLineageRequest,
    LineageEdge,
    LineageNode,
    LineageNodeKind,
    LineageRelation,
    ReproducibilityBundle,
    graph_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)

_ZERO_DIGEST = "sha256:" + ("0" * 64)


def artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    """Create a content-addressed fixture artifact without external I/O."""

    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest="sha256:" + (name.encode("utf-8").hex() * 64)[:64],
        media_type=media_type,
    )


def execution_context(*, denied_consent: bool = False) -> ExecutionContext:
    control_artifact = artifact("control-m2602")
    consent_state = ConsentState.WITHHELD if denied_consent else ConsentState.GRANTED
    return ExecutionContext(
        request_id="request-m2602",
        actor_id="fixture-actor-m2602",
        occurred_at=datetime(2026, 8, 16, 12, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=UpstreamDecisionReference(
                decision_id="approved-m2602",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=control_artifact,
            ),
            identity_lineage=IdentityLineageReference(
                decision_id="identity-m2602",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest="sha256:" + "1" * 64,
                evidence=control_artifact,
            ),
            provenance=UpstreamDecisionReference(
                decision_id="provenance-m2602",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=control_artifact,
            ),
            consent=ConsentReference(
                decision_id="consent-m2602",
                state=consent_state,
                policy_version="1.0.0",
                evidence=control_artifact,
            ),
            quality=UpstreamDecisionReference(
                decision_id="quality-m2602",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=control_artifact,
            ),
            support=UpstreamDecisionReference(
                decision_id="support-m2602",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=control_artifact,
            ),
            intended_use=UpstreamDecisionReference(
                decision_id="intended-use-m2602",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=control_artifact,
            ),
        ),
    )


def request(
    *,
    bad_digest: bool = False,
    cycle: bool = False,
    denied_consent: bool = False,
) -> BuildProteinSubtypeLineageRequest:
    """Build one frozen request, optionally selecting one hostile scenario."""

    nodes = tuple(
        LineageNode(
            node_id=f"node-{index}",
            kind=kind,
            name=f"{kind.value}-node",
            version="1.0.0",
            artifact=artifact(f"node-artifact-{index}"),
            producer=f"producer-{index}",
            node_digest="sha256:" + (f"{index:02x}" * 32),
        )
        for index, kind in enumerate(LineageNodeKind, start=1)
    )
    edges = tuple(
        LineageEdge(
            edge_id=f"edge-{index}",
            parent_node_id=f"node-{index}",
            child_node_id=f"node-{index + 1}",
            relation=LineageRelation.DERIVED_FROM,
        )
        for index in range(1, 7)
    )
    if cycle:
        edges = (
            *edges,
            LineageEdge(
                edge_id="edge-cycle",
                parent_node_id="node-7",
                child_node_id="node-1",
                relation=LineageRelation.DERIVED_FROM,
            ),
        )
    graph = {
        "graph_id": "graph-m2602",
        "version": "1.0.0",
        "nodes": nodes,
        "edges": edges,
        "graph_digest": _ZERO_DIGEST,
        "locked": True,
        "evidence": (),
    }
    graph_digest = graph_payload_digest(graph)
    upstream = artifact("m2601-registry", M2602_UPSTREAM_MEDIA_TYPE)
    return BuildProteinSubtypeLineageRequest(
        request_id="request-m2602",
        context=execution_context(denied_consent=denied_consent),
        graph_id="graph-m2602",
        graph_version="1.0.0",
        nodes=nodes,
        edges=edges,
        reproducibility_bundle=ReproducibilityBundle(
            bundle_id="bundle-m2602",
            version="1.0.0",
            root_node_ids=("node-1",),
            required_kinds=tuple(LineageNodeKind),
            graph_digest=("sha256:" + "f" * 64) if bad_digest else graph_digest,
            environment_digest="sha256:" + "2" * 64,
        ),
        upstream_registry_artifact=upstream,
        source_artifacts=(upstream, artifact("source-m2602")),
    )
