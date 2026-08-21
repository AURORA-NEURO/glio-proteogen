"""Deterministic M27-08 retirement workload with caller-declared controls."""

# Fixture constructors favor explicit immutable records over compact helpers.

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from glio_proteogen.contracts.m27_08 import (
    ArchiveStatus,
    CommunicationRecord,
    DependencyMigration,
    EvidencePreservation,
    LongTermArchive,
    MigrationStatus,
    RetireComplexActivityServiceRequest,
    RetirementConfiguration,
    RetirementCriterion,
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


def artifact(
    label: str, media_type: str = "application/vnd.glio-proteogen.m27-07+json"
) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"m2708.artifact.{label}",
        version="1.0.0",
        digest="sha256:" + hashlib.sha256(label.encode()).hexdigest(),
        media_type=media_type,
    )


def context(request_id: str, consent: ConsentState = ConsentState.GRANTED) -> ExecutionContext:
    def decision(label: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"m2708.decision.{label}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=artifact(f"decision-{label}", "application/json"),
        )

    return ExecutionContext(
        request_id=request_id,
        actor_id="m2708.actor.operator",
        occurred_at=datetime(2026, 8, 16, 12, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="m2708.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=artifact("identity-binding", "application/json").digest,
                evidence=artifact("identity", "application/json"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="m2708.consent",
                state=consent,
                policy_version="1.0.0",
                evidence=artifact("consent", "application/json"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def build_request(
    *,
    request_id: str = "m2708.request.default",
    consent: ConsentState = ConsentState.GRANTED,
    incomplete: bool = False,
    active_dependency: bool = False,
) -> RetireComplexActivityServiceRequest:
    evidence = (
        EvidenceReference(
            reference=artifact("criterion-evidence", "application/json"),
            role="evidence",
            claim="retirement control",
        ),
    )
    return RetireComplexActivityServiceRequest(
        request_id=request_id,
        context=context(request_id, consent),
        mass_spectrometry_proteome=artifact(
            "proteome", "application/vnd.glio-proteogen.m05-03+json"
        ),
        genome_transcriptome=artifact("genome", "application/vnd.glio-proteogen.m05-03+json"),
        ptm_annotations=artifact("ptm", "application/vnd.glio-proteogen.m05-03+json"),
        criteria=(
            RetirementCriterion(
                criterion_id="m2708.criterion.no-active",
                statement="No active production dependency remains.",
                satisfied=not incomplete,
                evidence=evidence,
            ),
        ),
        migrations=(
            DependencyMigration(
                migration_id="m2708.migration.main",
                dependency_id="active-service" if active_dependency else "retired-service",
                source_reference="m27-07",
                target_reference="archive://m27-08",
                owner="caller",
                status=(
                    MigrationStatus.IN_PROGRESS
                    if incomplete or active_dependency
                    else MigrationStatus.COMPLETED
                ),
                evidence=evidence,
            ),
        ),
        preserved_evidence=(
            EvidencePreservation(
                preservation_id="m2708.preservation.main",
                artifact=artifact("preserved", "application/json"),
                retention_class="long-term",
                retrievable=True,
                evidence=evidence,
            ),
        ),
        communications=(
            CommunicationRecord(
                communication_id="m2708.communication.main",
                audience="operators",
                message="Retirement package available.",
                acknowledged=not incomplete,
                evidence=evidence,
            ),
        ),
        archive=LongTermArchive(
            archive_id="m2708.archive.main",
            archive_reference="archive://m2708/main",
            retention_policy="indefinite",
            manifest=artifact("manifest", "application/json"),
            status=ArchiveStatus.VERIFIED if not incomplete else ArchiveStatus.PRESERVED,
            retrievable=True,
            evidence=evidence,
        ),
        configuration=RetirementConfiguration(
            configuration_id="m2708.config.default", version="1.0.0", evidence=evidence
        ),
        source_artifacts=(artifact("upstream-a"), artifact("upstream-b")),
    )


__all__ = ["artifact", "build_request"]
