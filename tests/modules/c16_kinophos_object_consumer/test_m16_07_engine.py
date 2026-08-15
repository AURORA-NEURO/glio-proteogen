"""Focused runtime and replay tests for provisional M16-07."""

# ruff: noqa: PLR2004

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m16_07 import (
    M1607_M1604_RESULT_MEDIA_TYPE,
    CompatibilityStatus,
    DownstreamField,
    ExportConfiguration,
    ExportPolicy,
    ExportProteinRnaDiscordanceDownstreamContractRequest,
    ExportStatus,
    FieldSupportStatus,
    ProteinRnaDiscordanceDownstreamExportResult,
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
from glio_proteogen.modules.c16_kinophos_object_consumer.m16_07_downstream_typed_export import (
    M1607AuthorizationError,
    M1607ExportEngine,
    M1607InferenceError,
    M1607ReplayVerificationError,
    M1607Service,
    export_protein_rna_discordance_downstream_contract,
    preflight_export_authorization,
)
from glio_proteogen.modules.c16_kinophos_object_consumer.m16_07_downstream_typed_export import (
    engine as engine_module,
)

_WHEN = datetime(2026, 1, 1, tzinfo=UTC)


def _artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1607": label}),
        media_type=media_type,
    )


def _context(*, accepted: bool = True) -> ExecutionContext:
    decision = UpstreamDecisionState.ACCEPTED if accepted else UpstreamDecisionState.REJECTED
    identity = IdentityLineageState.RESOLVED if accepted else IdentityLineageState.UNRESOLVED
    consent = ConsentState.GRANTED if accepted else ConsentState.WITHHELD
    return ExecutionContext(
        request_id="request.m1607",
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
    *,
    accepted: bool = True,
    label: str = "aligned",
    owner: str = "owner.proteogenomic",
    support_status: FieldSupportStatus = FieldSupportStatus.SUPPORTED,
) -> ExportProteinRnaDiscordanceDownstreamContractRequest:
    field = DownstreamField(
        field_id=f"field.proteotype.{label}",
        name=f"proteotype.{label}",
        value_type="string",
        owner=owner,
        support_status=support_status,
        source_artifact=_artifact("proteotype"),
    )
    configuration = ExportConfiguration(
        configuration_id=f"configuration.export.{label}",
        version="1.0.0",
        method="typed signed export",
        signature_reference=_artifact("signature"),
    )
    return ExportProteinRnaDiscordanceDownstreamContractRequest(
        request_id="request.m1607",
        context=_context(accepted=accepted),
        intended_use_result=_artifact("intended-use", M1607_M1604_RESULT_MEDIA_TYPE),
        policy=ExportPolicy(
            consumer_id="consumer.review",
            allowed_owner="owner.proteogenomic",
            required_media_type="application/json",
            configuration=configuration,
        ),
        fields=(field,),
        source_artifacts=(_artifact("proteome"), _artifact("transcriptome"), _artifact("ptm")),
    )


def test_supported_request_emits_signed_immutable_contract() -> None:
    result = M1607ExportEngine().export(_request())

    assert result.status is ExportStatus.SIGNED
    assert result.downstream_contract is not None
    assert result.compatibility_report.status is CompatibilityStatus.COMPATIBLE
    assert result.downstream_contract.immutable
    assert result.downstream_contract.consent_aware
    assert result.downstream_contract.support_aware
    assert result.support_decision.status is SupportStatus.SUPPORTED
    assert not result.human_review_required
    assert len(result.provenance.control_decisions) == 7
    assert result.uncertainty.transport.probability == 0.9


@pytest.mark.parametrize("label", ["warning", "conflict"])
def test_review_marker_abstains_with_review_compatibility(label: str) -> None:
    result = M1607ExportEngine().export(_request(label=label))

    assert result.status is ExportStatus.ABSTAINED
    assert result.downstream_contract is None
    assert result.compatibility_report.status is CompatibilityStatus.REVIEW_REQUIRED
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.human_review_required


def test_owner_or_support_mismatch_abstains() -> None:
    owner_result = M1607ExportEngine().export(_request(owner="owner.other"))
    assert owner_result.status is ExportStatus.ABSTAINED
    assert owner_result.compatibility_report.status is CompatibilityStatus.INCOMPATIBLE
    assert owner_result.support_decision.status is SupportStatus.UNSUPPORTED

    limited = M1607ExportEngine().export(_request(support_status=FieldSupportStatus.LIMITED))
    assert limited.status is ExportStatus.ABSTAINED
    assert limited.compatibility_report.status is CompatibilityStatus.INCOMPATIBLE


@pytest.mark.parametrize("label", ["unsupported", "ood", "missing", "kinase"])
def test_unsupported_or_prohibited_boundary_abstains_without_contract(label: str) -> None:
    result = M1607ExportEngine().export(_request(label=label))

    assert result.status is ExportStatus.ABSTAINED
    assert result.downstream_contract is None
    assert result.abstention_reason
    assert result.human_review_required


def test_service_public_operation_replay_and_tamper_are_deterministic() -> None:
    service = M1607Service()
    request = _request()
    first = service.execute(request)
    second = service.execute(request)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert service.verify(first).result_digest == first.result_digest
    assert service.verify(first, replay=False).result_digest == first.result_digest
    assert export_protein_rna_discordance_downstream_contract(request) == first
    with pytest.raises(M1607ReplayVerificationError):
        service.verify(
            first.model_copy(update={"result_digest": sha256_digest("tampered")}), replay=False
        )


def test_preflight_and_invalid_requests_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(M1607AuthorizationError):
        preflight_export_authorization({"context": {"references": {}}})
    with pytest.raises(M1607AuthorizationError):
        preflight_export_authorization(_request(accepted=False))
    with pytest.raises(M1607InferenceError):
        M1607ExportEngine().export(_request().model_copy(update={"fields": ()}))

    class BrokenAdapter:
        def validate_python(self, _payload: object, *, strict: bool) -> object:
            del strict
            raise ValueError

    monkeypatch.setattr(engine_module, "_RESULT_ADAPTER", BrokenAdapter())
    with pytest.raises(M1607InferenceError):
        M1607ExportEngine().export(_request())


def test_mapping_preflight_is_fail_closed() -> None:
    with pytest.raises(M1607AuthorizationError):
        preflight_export_authorization({"context": None})
    with pytest.raises(M1607AuthorizationError):
        preflight_export_authorization({"context": {"references": None}})

    class Hostile:
        def __getattr__(self, name: str) -> object:
            raise AssertionError(name)

    with pytest.raises(M1607AuthorizationError):
        preflight_export_authorization(Hostile())


def test_mapping_preflight_rejects_malformed_or_wrong_control_states() -> None:
    with pytest.raises(M1607AuthorizationError):
        preflight_export_authorization(
            {"context": {"references": {"approved_configuration": {"state": 1}}}}
        )
    with pytest.raises(M1607AuthorizationError):
        preflight_export_authorization(
            {
                "context": {
                    "references": {
                        "approved_configuration": {"state": "rejected"},
                    }
                }
            }
        )


def test_replay_rejects_reconstruction_failure_and_mismatch() -> None:
    request = _request()
    result = M1607ExportEngine().export(request)

    class FailingReplayEngine(M1607ExportEngine):
        def export(self, _request: object) -> ProteinRnaDiscordanceDownstreamExportResult:
            raise RuntimeError

    with pytest.raises(M1607ReplayVerificationError):
        FailingReplayEngine().verify(result)

    class MismatchedReplayEngine(M1607ExportEngine):
        def export(self, request: object) -> ProteinRnaDiscordanceDownstreamExportResult:
            return (
                M1607ExportEngine()
                .export(request)
                .model_copy(update={"result_digest": sha256_digest("different")})
            )

    with pytest.raises(M1607ReplayVerificationError):
        MismatchedReplayEngine().verify(result)
