"""Runtime, replay, preflight, and plugin parity coverage for M26-02."""

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m26_02 import (
    M2602_UPSTREAM_MEDIA_TYPE,
    BuildProteinSubtypeLineageRequest,
    LineageEdge,
    LineageNode,
    LineageNodeKind,
    LineageRelation,
    LineageStatus,
    ReproducibilityBundle,
    canonical_request_digest,
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
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c26_proteomics.m26_02_data_model_lineage_service import (
    LineageAuthorizationError,
    LineageReplayError,
    M2602LineageEngine,
    M2602LineagePlugin,
    M2602LineageService,
)

_ZERO = "sha256:" + ("0" * 64)


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest="sha256:" + (name.encode().hex() * 64)[:64],
        media_type=media_type,
    )


def _context() -> ExecutionContext:
    controls = _artifact("control")
    return ExecutionContext(
        request_id="request-m2602",
        actor_id="actor-m2602",
        occurred_at=datetime(2026, 8, 16, 12, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=UpstreamDecisionReference(
                decision_id="approved-m2602",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=controls,
            ),
            identity_lineage=IdentityLineageReference(
                decision_id="identity-m2602",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest="sha256:" + "1" * 64,
                evidence=controls,
            ),
            provenance=UpstreamDecisionReference(
                decision_id="provenance-m2602",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=controls,
            ),
            consent=ConsentReference(
                decision_id="consent-m2602",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=controls,
            ),
            quality=UpstreamDecisionReference(
                decision_id="quality-m2602",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=controls,
            ),
            support=UpstreamDecisionReference(
                decision_id="support-m2602",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=controls,
            ),
            intended_use=UpstreamDecisionReference(
                decision_id="intended-use-m2602",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=controls,
            ),
        ),
    )


def _request(*, graph_digest: str | None = None) -> BuildProteinSubtypeLineageRequest:
    nodes = tuple(
        LineageNode(
            node_id=f"node-{index}",
            kind=kind,
            name=f"{kind.value}-node",
            version="1.0.0",
            artifact=_artifact(f"node-artifact-{index}"),
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
    graph = {
        "graph_id": "graph-m2602",
        "version": "1.0.0",
        "nodes": nodes,
        "edges": edges,
        "graph_digest": _ZERO,
        "locked": True,
        "evidence": (),
    }
    computed_graph_digest = graph_payload_digest(graph)
    bundle = ReproducibilityBundle(
        bundle_id="bundle-m2602",
        version="1.0.0",
        root_node_ids=("node-1",),
        required_kinds=tuple(LineageNodeKind),
        graph_digest=graph_digest or computed_graph_digest,
        environment_digest="sha256:" + "2" * 64,
    )
    upstream = _artifact("m2601-registry", M2602_UPSTREAM_MEDIA_TYPE)
    return BuildProteinSubtypeLineageRequest(
        request_id="request-m2602",
        context=_context(),
        graph_id="graph-m2602",
        graph_version="1.0.0",
        nodes=nodes,
        edges=edges,
        reproducibility_bundle=bundle,
        upstream_registry_artifact=upstream,
        source_artifacts=(upstream, _artifact("source-m2602")),
    )


def test_supported_lineage_is_deterministic_and_replayable() -> None:
    request = _request()
    service = M2602LineageService()
    first = service.execute(request)
    second = service.execute(request)
    assert first.status is LineageStatus.BUILT
    assert first.result_digest == second.result_digest
    assert first.request_digest == canonical_request_digest(request)
    assert first.lineage_graph is not None
    assert first.reproducibility_bundle is not None
    assert first.support_decision.status is SupportStatus.SUPPORTED
    assert service.verify(first).result_digest == first.result_digest


def test_bad_graph_digest_abstains_without_negative_finding() -> None:
    result = M2602LineageEngine().build(_request(graph_digest="sha256:" + "f" * 64))
    assert result.status is LineageStatus.ABSTAINED
    assert result.lineage_graph is None
    assert result.reproducibility_bundle is None
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert any(item.code.value == "reproducibility_gap" for item in result.findings)
    assert result.abstention_reason is not None
    assert "negative" not in result.abstention_reason.lower()


def test_denied_control_fails_before_graph_traversal() -> None:
    payload = _request().model_dump(mode="python")
    payload["context"]["references"]["consent"]["state"] = ConsentState.WITHHELD
    with pytest.raises(LineageAuthorizationError):
        M2602LineageService().execute(payload)


def test_plugin_parse_once_and_raw_tamper_are_closed() -> None:
    request = _request()
    plugin = M2602LineagePlugin(M2602LineageService())
    validated = plugin.validate(json.dumps(request.model_dump(mode="json"), sort_keys=True))
    result = plugin.run(validated)
    assert result.result_digest == M2602LineageService().execute(request).result_digest
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(request)  # type: ignore[arg-type]
    tampered = result.model_copy(update={"result_id": "tampered-result"})
    with pytest.raises((ValidationError, LineageReplayError)):
        M2602LineageService.verify(tampered)
