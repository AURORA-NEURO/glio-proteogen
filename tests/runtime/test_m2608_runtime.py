"""Runtime, seven-control preflight, safe abstention and replay tests for M26-08."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m26_08 import (
    ArchiveStatus,
    CommunicationRecord,
    DependencyMigration,
    EvidencePreservation,
    LongTermArchive,
    MigrationStatus,
    RetirementConfiguration,
    RetirementCriterion,
    RetirementStatus,
    RetireProteinSubtypeServiceRequest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_08_retirement_archival_knowledge_transfer import (  # noqa: E501
    M2608AuthorizationError,
    M2608Plugin,
    M2608ReplayError,
    M2608RetirementService,
    M2608TokenError,
    RetirementSubmission,
    preflight_m2608_authorization,
)


def _digest(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode()).hexdigest()


def _artifact(label: str, *, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=_digest(label),
        media_type=media_type,
    )


def _context(
    *, quality_state: UpstreamDecisionState = UpstreamDecisionState.ACCEPTED
) -> ExecutionContext:
    def decision(
        role: str, state: UpstreamDecisionState = UpstreamDecisionState.ACCEPTED
    ) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.{role}",
            state=state,
            policy_version="1.0.0",
            evidence=_artifact(role),
        )

    return ExecutionContext(
        request_id="request.m2608",
        actor_id="actor.scientific-reviewer",
        occurred_at=datetime(2026, 8, 16, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=_digest("identity"),
                evidence=_artifact("identity"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=decision("quality", quality_state),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def _evidence(label: str = "retirement") -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(label),
        role="evidence",
        claim="Caller-declared immutable M26-08 evidence.",
    )


def _request(  # noqa: PLR0913
    *,
    context: ExecutionContext | None = None,
    criterion_satisfied: bool = True,
    migration_status: MigrationStatus = MigrationStatus.COMPLETED,
    evidence_retrievable: bool = True,
    communication_acknowledged: bool = True,
    archive_status: ArchiveStatus = ArchiveStatus.VERIFIED,
    archive_retrievable: bool = True,
    active_dependencies: tuple[str, ...] = (),
) -> RetireProteinSubtypeServiceRequest:
    criterion = RetirementCriterion(
        criterion_id="criterion.m2608.no-active-dependency",
        statement="No active dependency remains after migration.",
        satisfied=criterion_satisfied,
        evidence=(_evidence("criterion"),),
    )
    migration = DependencyMigration(
        migration_id="migration.m2608.service-v1",
        dependency_id="dependency.m2608.service",
        source_reference="service-v1",
        target_reference="signed-bundle-v2",
        owner="owner.scientific-engineering",
        status=migration_status,
        evidence=(_evidence("migration"),),
    )
    preservation = EvidencePreservation(
        preservation_id="preservation.m2608.archive-manifest",
        artifact=_artifact("archive-manifest"),
        retention_class="long-term",
        checksum_verified=evidence_retrievable,
        retrievable=evidence_retrievable,
        evidence=(_evidence("preservation"),),
    )
    communication = CommunicationRecord(
        communication_id="communication.m2608.operators",
        audience="operators",
        message="The retiring service is available in the signed archive.",
        acknowledged=communication_acknowledged,
        evidence=(_evidence("communication"),),
    )
    archive = LongTermArchive(
        archive_id="archive.m2608.signed-bundle",
        archive_reference="archive://m2608/protein-subtype",
        retention_policy="long-term immutable retention",
        manifest=_artifact("archive-manifest"),
        status=archive_status,
        retrievable=archive_retrievable,
        evidence=(_evidence("archive"),),
    )
    configuration = RetirementConfiguration(
        configuration_id="configuration.m2608.locked",
        version="1.0.0",
        active_dependencies=active_dependencies,
    )
    return RetireProteinSubtypeServiceRequest(
        request_id="request.m2608",
        context=context or _context(),
        mass_spectrometry_proteome=_artifact("mass-spectrometry"),
        genome_transcriptome=_artifact("genome-transcriptome"),
        ptm_annotations=_artifact("ptm-annotations"),
        criteria=(criterion,),
        migrations=(migration,),
        preserved_evidence=(preservation,),
        communications=(communication,),
        archive=archive,
        configuration=configuration,
        source_artifacts=(
            _artifact("mass-spectrometry"),
            _artifact("genome-transcriptome"),
            _artifact("ptm-annotations"),
        ),
    )


def test_service_executes_closed_package_and_replays_deterministically() -> None:
    service = M2608RetirementService()
    request = _request()

    first = service.retire(request)
    second = service.retire(request)

    assert first.status.value == RetirementStatus.EXECUTED.value
    assert first.package is not None
    assert first.package.status is RetirementStatus.EXECUTED
    assert first.package.archive.status is ArchiveStatus.VERIFIED
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert service.verify(first).model_dump(mode="json") == first.model_dump(mode="json")


@pytest.mark.parametrize(
    ("field", "expected_code"),
    [
        ("criterion", "criterion_unsatisfied"),
        ("migration", "dependency_migration_incomplete"),
        ("evidence", "evidence_not_retrievable"),
        ("communication", "communication_unacknowledged"),
        ("archive", "archive_unverified"),
        ("active", "active_dependency"),
    ],
)
def test_each_retirement_gate_abstains_without_package(field: str, expected_code: str) -> None:
    if field == "criterion":
        request = _request(criterion_satisfied=False)
    elif field == "migration":
        request = _request(migration_status=MigrationStatus.BLOCKED)
    elif field == "evidence":
        request = _request(evidence_retrievable=False)
    elif field == "communication":
        request = _request(communication_acknowledged=False)
    elif field == "archive":
        request = _request(archive_status=ArchiveStatus.PRESERVED)
    else:
        request = _request(active_dependencies=("dependency.m2608.active",))

    result = M2608RetirementService().retire(request)

    assert result.status.value == "abstained"
    assert result.package is None
    assert result.abstention_reason is not None
    assert any(finding.code.value == expected_code for finding in result.findings)


def test_failed_context_control_is_fail_closed() -> None:
    with pytest.raises(M2608AuthorizationError):
        M2608RetirementService().retire(
            _request(context=_context(quality_state=UpstreamDecisionState.REJECTED))
        )


def test_replay_rejects_tampered_result_digest() -> None:
    result = M2608RetirementService().retire(_request())
    tampered = result.model_copy(update={"result_digest": _digest("tampered")})

    with pytest.raises(M2608ReplayError):
        M2608RetirementService.verify(tampered)


def test_replay_rejects_tampered_request_digest() -> None:
    result = M2608RetirementService().retire(_request())
    tampered = result.model_copy(update={"request_digest": _digest("tampered")})

    with pytest.raises(M2608ReplayError):
        M2608RetirementService.verify(tampered)


def test_plugin_requires_token_and_preserves_json_parity() -> None:
    plugin = M2608Plugin()
    request = _request()
    token = plugin.validate(RetirementSubmission(request.model_dump_json()))
    result = plugin.run(token)

    assert result.package is not None
    assert plugin.replay(result).result_digest == result.result_digest
    with pytest.raises(M2608TokenError):
        plugin.run(object())  # type: ignore[arg-type]
    with pytest.raises(M2608TokenError):
        plugin.validate(request)  # type: ignore[arg-type]


def test_hostile_preflight_mapping_fails_closed() -> None:
    with pytest.raises(M2608AuthorizationError):
        preflight_m2608_authorization({"context": {"references": object()}})


def test_request_rejects_duplicate_source_artifact_ids() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="source artifact identifiers"):
        RetireProteinSubtypeServiceRequest.model_validate(
            request.model_dump(mode="python")
            | {"source_artifacts": (request.source_artifacts[0],) * 2}
        )
