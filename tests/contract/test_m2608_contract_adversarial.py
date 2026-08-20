"""Adversarial closure tests for the provisional M26-08 contract spine."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m26_08 import (
    M2608_DOSSIER_SHA256,
    M2608_DOSSIER_SLICE,
    ArchiveStatus,
    CommunicationRecord,
    DependencyMigration,
    EvidencePreservation,
    LongTermArchive,
    MigrationStatus,
    ProteinSubtypeRetirementResult,
    RetirementConfiguration,
    RetirementCriterion,
    RetirementPackage,
    RetirementRunStatus,
    RetirementStatus,
    RetireProteinSubtypeServiceRequest,
)
from glio_proteogen.contracts.m26_08.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    EvidenceReference,
    SupportStatus,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_08_retirement_archival_knowledge_transfer import (  # noqa: E501
    M2608RetirementService,
)
from tests.runtime.test_m2608_runtime import _request

_SHA256_HEX_LENGTH = 64


def _artifact(identifier: str, marker: str = "a") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=identifier,
        version="0.1.0",
        digest="sha256:" + marker * 64,
        media_type="application/json",
    )


def _evidence(identifier: str = "evidence-1") -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(identifier, "b"),
        role="evidence",
        claim="Caller-declared immutable retirement evidence.",
    )


def _criterion(identifier: str = "criterion-1") -> RetirementCriterion:
    return RetirementCriterion(
        criterion_id=identifier,
        statement="No active dependency remains after migration.",
        satisfied=True,
        evidence=(_evidence(),),
    )


def _migration(
    identifier: str = "migration-1",
    *,
    source: str = "service-v1",
    target: str = "bundle-v2",
) -> DependencyMigration:
    return DependencyMigration(
        migration_id=identifier,
        dependency_id="dependency-1",
        source_reference=source,
        target_reference=target,
        owner="owner-1",
        status=MigrationStatus.COMPLETED,
        evidence=(_evidence(),),
    )


def _preservation(identifier: str = "preservation-1") -> EvidencePreservation:
    return EvidencePreservation(
        preservation_id=identifier,
        artifact=_artifact("archive-manifest", "c"),
        retention_class="long-term",
        retrievable=True,
        evidence=(_evidence(),),
    )


def _communication(identifier: str = "communication-1") -> CommunicationRecord:
    return CommunicationRecord(
        communication_id=identifier,
        audience="operators",
        message="The retired service is available in the signed archive.",
        acknowledged=True,
        evidence=(_evidence(),),
    )


def _configuration() -> RetirementConfiguration:
    return RetirementConfiguration(
        configuration_id="configuration-1",
        version="0.1.0",
    )


def _archive() -> LongTermArchive:
    return LongTermArchive(
        archive_id="archive-1",
        archive_reference="archive://m2608/protein-subtype",
        retention_policy="long-term immutable retention",
        manifest=_artifact("archive-manifest", "c"),
        status=ArchiveStatus.VERIFIED,
        retrievable=True,
        evidence=(_evidence(),),
    )


def _package(**changes: object) -> RetirementPackage:
    values: dict[str, object] = {
        "package_id": "package-1",
        "version": "0.1.0",
        "status": RetirementStatus.EXECUTED,
        "criteria": (_criterion(),),
        "migrations": (_migration(),),
        "preserved_evidence": (_preservation(),),
        "communications": (_communication(),),
        "archive": _archive(),
        "configuration": _configuration(),
        "package_digest": "sha256:" + "e" * 64,
        "evidence": (_evidence(),),
    }
    values.update(changes)
    return RetirementPackage.model_validate(values)


def test_authority_slice_is_pinned_and_provisional() -> None:
    assert len(M2608_DOSSIER_SHA256) == _SHA256_HEX_LENGTH
    assert M2608_DOSSIER_SLICE.endswith(":9344-9384")


def test_executed_package_accepts_closed_evidence_graph() -> None:
    package = _package()
    assert package.status.value == "executed"
    assert package.archive.manifest.artifact_id == "archive-manifest"


def test_archive_manifest_must_be_preserved() -> None:
    with pytest.raises(ValidationError, match="manifest must be present"):
        _package(
            preserved_evidence=(
                EvidencePreservation(
                    preservation_id="preservation-1",
                    artifact=_artifact("different-artifact", "c"),
                    retention_class="long-term",
                    retrievable=True,
                    evidence=(_evidence(),),
                ),
            )
        )


def test_completed_migration_must_change_reference() -> None:
    with pytest.raises(ValidationError, match="must change"):
        _package(migrations=(_migration(source="same", target="same"),))


def test_duplicate_criterion_ids_are_rejected() -> None:
    with pytest.raises(ValidationError, match="identifiers must be unique"):
        _package(criteria=(_criterion("same"), _criterion("same")))


def test_duplicate_migration_ids_are_rejected() -> None:
    with pytest.raises(ValidationError, match="identifiers must be unique"):
        _package(migrations=(_migration("same"), _migration("same")))


def test_unretrievable_verified_archive_is_rejected() -> None:
    with pytest.raises(ValidationError, match="verified archive must be retrievable"):
        LongTermArchive(
            archive_id="archive-2",
            archive_reference="archive://m2608/missing",
            retention_policy="long-term immutable retention",
            manifest=_artifact("missing-manifest", "d"),
            status=ArchiveStatus.VERIFIED,
            retrievable=False,
            evidence=(_evidence(),),
        )


def test_unretrievable_archive_cannot_claim_retrievability() -> None:
    with pytest.raises(ValidationError, match="unretrievable archive"):
        LongTermArchive(
            archive_id="archive-2",
            archive_reference="archive://m2608/missing",
            retention_policy="long-term immutable retention",
            manifest=_artifact("missing-manifest", "d"),
            status=ArchiveStatus.UNRETRIEVABLE,
            retrievable=True,
            evidence=(_evidence(),),
        )


def test_canonical_digest_is_deterministic_for_equivalent_models() -> None:
    first = {"request_id": "request-1", "occurred_at": datetime(2026, 1, 1, tzinfo=UTC)}
    second = {"occurred_at": datetime(2026, 1, 1, tzinfo=UTC), "request_id": "request-1"}
    assert canonical_request_digest(first) == canonical_request_digest(second)


def test_checksum_verified_evidence_cannot_be_unretrievable() -> None:
    with pytest.raises(ValidationError, match="checksum-verified preservation"):
        EvidencePreservation(
            preservation_id="preservation-bad",
            artifact=_artifact("archive-bad", "c"),
            retention_class="long-term",
            checksum_verified=True,
            retrievable=False,
            evidence=(_evidence(),),
        )


def test_package_allows_nonexecuted_review_state() -> None:
    package = _package(status=RetirementStatus.PROPOSED)
    assert package.status is RetirementStatus.PROPOSED


def test_executed_package_rejects_active_dependency() -> None:
    configuration = _configuration().model_copy(
        update={"active_dependencies": ("dependency.active",)}
    )
    with pytest.raises(ValidationError, match="active dependencies"):
        _package(configuration=configuration)


def test_executed_package_rejects_unsatisfied_criterion() -> None:
    with pytest.raises(ValidationError, match="unsatisfied criteria"):
        _package(criteria=(_criterion().model_copy(update={"satisfied": False}),))


def test_executed_package_rejects_incomplete_migration() -> None:
    with pytest.raises(ValidationError, match="completed dependency migrations"):
        _package(migrations=(_migration().model_copy(update={"status": MigrationStatus.BLOCKED}),))


def test_executed_package_rejects_unretrievable_evidence() -> None:
    preservation = _preservation().model_copy(
        update={"checksum_verified": False, "retrievable": False}
    )
    with pytest.raises(ValidationError, match="retrievable preserved evidence"):
        _package(preserved_evidence=(preservation,))


def test_executed_package_rejects_unacknowledged_communication() -> None:
    communication = _communication().model_copy(update={"acknowledged": False})
    with pytest.raises(ValidationError, match="acknowledged communications"):
        _package(communications=(communication,))


def test_executed_package_rejects_unverified_archive() -> None:
    archive = _archive().model_copy(update={"status": ArchiveStatus.PRESERVED})
    with pytest.raises(ValidationError, match="verified archive"):
        _package(archive=archive)


def test_request_rejects_duplicate_groups() -> None:
    request = _request()
    duplicate = request.model_dump(mode="python") | {
        "criteria": (request.criteria[0], request.criteria[0])
    }
    with pytest.raises(ValidationError, match="unique within"):
        RetireProteinSubtypeServiceRequest.model_validate(duplicate)


def test_request_rejects_missing_archive_manifest() -> None:
    request = _request()
    preservation = request.preserved_evidence[0].model_copy(
        update={"artifact": _artifact("different-preservation")}
    )
    with pytest.raises(ValidationError, match="archive manifest"):
        RetireProteinSubtypeServiceRequest.model_validate(
            request.model_dump(mode="python") | {"preserved_evidence": (preservation,)}
        )


def test_request_rejects_duplicate_source_modalities() -> None:
    request = _request()
    duplicate = request.mass_spectrometry_proteome
    with pytest.raises(ValidationError, match="source modality"):
        RetireProteinSubtypeServiceRequest.model_validate(
            request.model_dump(mode="python")
            | {
                "genome_transcriptome": duplicate,
                "source_artifacts": (duplicate, request.ptm_annotations),
            }
        )


def test_request_rejects_missing_or_rehashed_source_modality() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="bind every declared source modality"):
        RetireProteinSubtypeServiceRequest.model_validate(
            request.model_dump(mode="python") | {"source_artifacts": request.source_artifacts[:2]}
        )
    forged = request.mass_spectrometry_proteome.model_copy(update={"digest": "sha256:" + "f" * 64})
    with pytest.raises(ValidationError, match="bind every declared source modality"):
        RetireProteinSubtypeServiceRequest.model_validate(
            request.model_dump(mode="python")
            | {"source_artifacts": (forged, *request.source_artifacts[1:])}
        )


def test_result_status_closure_is_enforced() -> None:
    service = M2608RetirementService()
    executed = service.retire(_request())
    with pytest.raises(ValidationError, match="supported retirement package"):
        ProteinSubtypeRetirementResult.model_validate(
            executed.model_dump(mode="python") | {"package": None}
        )
    abstained = service.retire(_request(criterion_satisfied=False))
    assert executed.package is not None
    with pytest.raises(ValidationError, match="safe status"):
        ProteinSubtypeRetirementResult.model_validate(
            abstained.model_dump(mode="python")
            | {
                "status": RetirementRunStatus.ABSTAINED,
                "package": executed.package,
                "support_decision": abstained.support_decision.model_copy(
                    update={"status": SupportStatus.SUPPORTED}
                ),
            }
        )


def test_executed_result_rejects_self_rehashed_package_control_mutation() -> None:
    service = M2608RetirementService()
    result = service.retire(_request())
    assert result.package is not None
    forged_preservation = result.package.preserved_evidence[0].model_copy(
        update={"retention_class": "forged-retention"}
    )
    forged_package = result.package.model_copy(
        update={
            "preserved_evidence": (
                forged_preservation,
                *result.package.preserved_evidence[1:],
            )
        }
    )
    forged = result.model_copy(update={"package": forged_package})
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})
    with pytest.raises(ValidationError, match="exact request retirement controls"):
        ProteinSubtypeRetirementResult.model_validate(forged.model_dump(mode="python"), strict=True)
