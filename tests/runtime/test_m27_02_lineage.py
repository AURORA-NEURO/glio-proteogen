"""Runtime, replay, and plugin coverage for M27-02."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m27_02 import (
    M2702_M2701_INPUT_MEDIA_TYPE,
    ComplexActivityLineageResult,
    LineageStatus,
    ResolveComplexActivityLineageRequest,
    graph_payload_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
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
from glio_proteogen.modules.c27_complex_activity.m27_02_lineage_service import (
    M2702AuthorizationError,
    M2702LineageResolver,
    M2702Plugin,
    M2702Service,
)


def _artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m2702.{label}",
        version="1.0.0",
        digest=sha256_digest({"m2702": label}),
        media_type=media_type,
    )


def _decision(role: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.m2702.{role}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=_artifact(f"control.{role}"),
    )


def _context() -> ExecutionContext:
    return ExecutionContext(
        request_id="request.m2702.synthetic",
        actor_id="actor.m2702.synthetic",
        occurred_at=datetime(2026, 8, 16, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m2702.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest({"subject": "synthetic"}),
                evidence=_artifact("control.identity"),
            ),
            provenance=_decision("provenance"),
            consent=ConsentReference(
                decision_id="decision.m2702.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("control.consent"),
            ),
            quality=_decision("quality"),
            support=_decision("support"),
            intended_use=_decision("intended_use"),
        ),
    )


def _request(*, duplicate: bool = False) -> ResolveComplexActivityLineageRequest:
    upstream = _artifact("upstream", M2702_M2701_INPUT_MEDIA_TYPE)
    secondary = _artifact("secondary")
    artifacts = (upstream, secondary, upstream) if duplicate else (upstream, secondary)
    return ResolveComplexActivityLineageRequest(
        request_id="request.m2702.synthetic",
        context=_context(),
        upstream_result=upstream,
        root_object_id="activity.m2702.root",
        source_artifacts=artifacts,
    )


_EXPECTED_NODE_COUNT = 3
_EXPECTED_EDGE_COUNT = 2
_EXPECTED_CONTROL_COUNT = 7


def test_runtime_resolves_multi_source_graph_and_replays_exactly() -> None:
    request = _request()
    first = M2702LineageResolver().resolve(request)
    second = M2702Service().execute(request)

    assert first == second
    assert first.status is LineageStatus.RESOLVED
    assert first.lineage_graph is not None
    assert len(first.lineage_graph.nodes) == _EXPECTED_NODE_COUNT
    assert len(first.lineage_graph.edges) == _EXPECTED_EDGE_COUNT
    assert first.lineage_graph.reproducibility_bundle.manifest_digest == graph_payload_digest(
        first.lineage_graph
    )
    assert len(first.provenance.control_decisions) == _EXPECTED_CONTROL_COUNT
    assert first.emits_parent is False
    assert M2702Service().verify(first)


def test_replay_rejects_self_rehashed_semantic_mutation() -> None:
    result = M2702LineageResolver().resolve(_request())
    mutated_support = result.support_decision.model_copy(
        update={"rationale": "caller-rehashed lineage mutation"}
    )
    forged = result.model_copy(update={"support_decision": mutated_support})
    rehashed = forged.model_copy(update={"result_digest": result_payload_digest(forged)})

    assert not M2702Service().verify(rehashed)


def test_replay_rejects_stale_request_identity_after_rehash() -> None:
    result = M2702LineageResolver().resolve(_request())
    changed = _request().model_copy(update={"root_object_id": "m2702.changed-root"})
    forged = result.model_copy(update={"request": changed})
    rehashed = forged.model_copy(update={"result_digest": result_payload_digest(forged)})

    assert not M2702Service().verify(rehashed)


def test_duplicate_source_identifier_abstains_without_graph() -> None:
    result = M2702LineageResolver().resolve(_request(duplicate=True))

    assert result.status is LineageStatus.ABSTAINED
    assert result.lineage_graph is None
    assert result.support_decision.status.value == "unsupported"
    assert result.findings[0].code.value == "broken_link"
    assert result.safe_failure_report is not None


def test_plugin_strict_json_validate_then_run_matches_typed_request() -> None:
    request = _request()
    plugin = M2702Plugin(M2702Service())
    token = plugin.validate(canonical_json_bytes(request.model_dump(mode="json")))

    assert plugin.run(token) == M2702LineageResolver().resolve(request)
    forged = type(token)(request=token.request)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]


def test_authorization_fails_before_unsupported_control_is_used() -> None:
    denied = _context().model_copy(
        update={
            "references": _context().references.model_copy(update={"support": _decision("support")})
        }
    )
    denied = denied.model_copy(
        update={
            "references": denied.references.model_copy(
                update={
                    "consent": denied.references.consent.model_copy(
                        update={"state": ConsentState.WITHHELD}
                    )
                }
            )
        }
    )
    request = _request().model_copy(update={"context": denied})

    with pytest.raises(M2702AuthorizationError):
        M2702LineageResolver().resolve(request)


def test_result_replay_rejects_tampered_digest() -> None:
    result = M2702LineageResolver().resolve(_request())

    with pytest.raises(ValidationError, match="result digest"):
        ComplexActivityLineageResult.model_validate(
            result.model_copy(update={"result_digest": "sha256:" + "f" * 64}),
            strict=True,
        )
