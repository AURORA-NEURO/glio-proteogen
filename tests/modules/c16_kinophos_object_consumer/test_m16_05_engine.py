"""Focused runtime and replay tests for provisional M16-05."""

# ruff: noqa: E501, PLR2004

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m16_05 import (
    M1605_M1604_INPUT_MEDIA_TYPE,
    PresentProteinRnaReviewWorkspaceRequest,
    WorkspaceConfiguration,
    WorkspaceItemStatus,
    WorkspacePresentationStatus,
    WorkspaceViewKind,
)
from glio_proteogen.kernel.canonical import sha256_digest
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
from glio_proteogen.modules.c16_kinophos_object_consumer.m16_05_workflow_presentation_service import (
    M1605AuthorizationError,
    M1605InferenceError,
    M1605PresentationEngine,
    M1605ReplayVerificationError,
    M1605Service,
    preflight_workspace_authorization,
    present_protein_rna_review_workspace,
)
from glio_proteogen.modules.c16_kinophos_object_consumer.m16_05_workflow_presentation_service import (
    engine as engine_module,
)

_WHEN = datetime(2026, 1, 1, tzinfo=UTC)


def _artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1605": label}),
        media_type=media_type,
    )


def _context(*, accepted: bool = True) -> ExecutionContext:
    decision = UpstreamDecisionState.ACCEPTED if accepted else UpstreamDecisionState.REJECTED
    identity = IdentityLineageState.RESOLVED if accepted else IdentityLineageState.UNRESOLVED
    consent = ConsentState.GRANTED if accepted else ConsentState.WITHHELD
    return ExecutionContext(
        request_id="request.m1605",
        actor_id="actor.test",
        occurred_at=_WHEN,
        references=ContextReferences(
            approved_configuration=UpstreamDecisionReference(
                decision_id="decision.configuration",
                state=decision,
                policy_version="1.0.0",
                evidence=_artifact("configuration"),
            ),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=identity,
                policy_version="1.0.0",
                binding_digest=sha256_digest("identity"),
                evidence=_artifact("identity"),
            ),
            provenance=UpstreamDecisionReference(
                decision_id="decision.provenance",
                state=decision,
                policy_version="1.0.0",
                evidence=_artifact("provenance"),
            ),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=consent,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=UpstreamDecisionReference(
                decision_id="decision.quality",
                state=decision,
                policy_version="1.0.0",
                evidence=_artifact("quality"),
            ),
            support=UpstreamDecisionReference(
                decision_id="decision.support",
                state=decision,
                policy_version="1.0.0",
                evidence=_artifact("support"),
            ),
            intended_use=UpstreamDecisionReference(
                decision_id="decision.intended",
                state=decision,
                policy_version="1.0.0",
                evidence=_artifact("intended"),
            ),
        ),
    )


def _request(
    *, accepted: bool = True, label: str = "aligned"
) -> PresentProteinRnaReviewWorkspaceRequest:
    kinds = tuple(WorkspaceViewKind)
    return PresentProteinRnaReviewWorkspaceRequest(
        request_id="request.m1605",
        context=_context(accepted=accepted),
        upstream_result=_artifact("upstream", M1605_M1604_INPUT_MEDIA_TYPE),
        configuration=WorkspaceConfiguration(
            configuration_id=f"configuration.workspace.{label}",
            version="1.0.0",
            default_view_order=kinds,
            visible_sections=kinds,
        ),
        source_artifacts=(_artifact("proteome"), _artifact("transcriptome"), _artifact("ptm")),
    )


def test_presented_workspace_has_all_safe_views_and_provenance() -> None:
    result = M1605PresentationEngine().present(_request())

    assert result.status is WorkspacePresentationStatus.PRESENTED
    assert result.workspace is not None
    assert {view.kind for view in result.workspace.views} == set(WorkspaceViewKind)
    assert all(view.safe_default for view in result.workspace.views)
    assert all(
        view.items[0].status is WorkspaceItemStatus.AVAILABLE for view in result.workspace.views
    )
    assert result.support_decision.status is SupportStatus.SUPPORTED
    assert not result.human_review_required
    assert result.uncertainty.transport.probability == 0.9
    assert len(result.provenance.control_decisions) == 7


def test_warning_workspace_preserves_discrepancy_and_requires_review() -> None:
    result = M1605PresentationEngine().present(_request(label="warning"))

    assert result.status is WorkspacePresentationStatus.REVIEW_REQUIRED
    assert result.workspace is not None
    discrepancy = next(
        view for view in result.workspace.views if view.kind is WorkspaceViewKind.DISCREPANCY
    )
    assert discrepancy.items[0].status is WorkspaceItemStatus.WARNING
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.human_review_required


@pytest.mark.parametrize("label", ["unsupported", "ood", "missing"])
def test_unsupported_workspace_abstains_without_workspace(label: str) -> None:
    result = M1605PresentationEngine().present(_request(label=label))

    assert result.status is WorkspacePresentationStatus.ABSTAINED
    assert result.workspace is None
    assert result.abstention_reason
    assert result.support_decision.status is SupportStatus.UNSUPPORTED
    assert result.human_review_required


def test_prohibited_boundary_abstains() -> None:
    result = M1605PresentationEngine().present(_request(label="kinase"))

    assert result.status is WorkspacePresentationStatus.ABSTAINED
    assert result.workspace is None
    assert "upstream_unsupported" in {item.value for item in result.findings}


def test_service_operation_replay_and_tamper_are_deterministic() -> None:
    service = M1605Service()
    request = _request()
    first = service.execute(request)
    second = service.execute(request)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert service.verify(first).result_digest == first.result_digest
    assert service.verify(first, replay=False).result_digest == first.result_digest
    assert present_protein_rna_review_workspace(request) == first
    with pytest.raises(M1605ReplayVerificationError):
        service.verify(
            first.model_copy(update={"result_digest": sha256_digest("tampered")}), replay=False
        )


def test_preflight_and_invalid_requests_fail_closed() -> None:
    with pytest.raises(M1605AuthorizationError):
        preflight_workspace_authorization({"context": {"references": {}}})
    with pytest.raises(M1605AuthorizationError):
        preflight_workspace_authorization(_request(accepted=False))
    with pytest.raises(M1605InferenceError):
        M1605PresentationEngine().present(_request().model_copy(update={"source_artifacts": ()}))


def test_mapping_preflight_and_hostile_object_are_rejected() -> None:
    with pytest.raises(M1605AuthorizationError):
        preflight_workspace_authorization({"context": None})
    with pytest.raises(M1605AuthorizationError):
        preflight_workspace_authorization({"context": {"references": None}})

    class Hostile:
        def __getattr__(self, name: str) -> object:
            raise AssertionError(name)

    with pytest.raises(M1605AuthorizationError):
        preflight_workspace_authorization(Hostile())

    class BrokenMapping(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            del key, default
            raise RuntimeError

    with pytest.raises(M1605AuthorizationError):
        preflight_workspace_authorization({"context": BrokenMapping()})


def test_mapping_preflight_rejects_non_string_and_wrong_control_states() -> None:
    with pytest.raises(M1605AuthorizationError):
        preflight_workspace_authorization(
            {"context": {"references": {"approved_configuration": {"state": None}}}}
        )
    refs = {
        role: {"state": "accepted"}
        for role in (
            "approved_configuration",
            "identity_lineage",
            "provenance",
            "consent",
            "quality",
            "support",
            "intended_use",
        )
    }
    with pytest.raises(M1605AuthorizationError):
        preflight_workspace_authorization({"context": {"references": refs}})


def test_engine_replay_and_result_adapter_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = M1605PresentationEngine()
    result = engine.present(_request())
    with pytest.raises(M1605ReplayVerificationError):
        engine.verify(
            result.model_copy(update={"result_digest": sha256_digest("tampered")}), replay=False
        )

    class BrokenAdapter:
        def validate_python(self, _payload: object, *, strict: bool) -> object:
            del strict
            raise ValueError

    monkeypatch.setattr(engine_module, "_RESULT_ADAPTER", BrokenAdapter())
    with pytest.raises(M1605InferenceError):
        engine.present(_request())


def test_engine_replay_exception_and_mismatch_are_rejected() -> None:
    result = M1605PresentationEngine().present(_request())

    class BrokenReplayEngine(M1605PresentationEngine):
        def present(self, request: object):  # type: ignore[no-untyped-def]
            del request
            raise ValueError

    with pytest.raises(M1605ReplayVerificationError):
        BrokenReplayEngine().verify(result)

    class MismatchEngine(M1605PresentationEngine):
        def present(self, request: object):  # type: ignore[no-untyped-def]
            del request
            return M1605PresentationEngine().present(_request(label="warning"))

    with pytest.raises(M1605ReplayVerificationError):
        MismatchEngine().verify(result)
