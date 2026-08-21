"""M27-08 adversarial closure tests."""

# Adversarial tests deliberately use broad validation boundaries.
# ruff: noqa: PT011, RUF005

import pytest
from evals.m27_08.fixture import build_request

from glio_proteogen.contracts.m27_08 import (
    ArchiveStatus,
    EvidencePreservation,
    LongTermArchive,
    MigrationStatus,
    RetirementPackage,
    RetirementStatus,
)
from glio_proteogen.contracts.m27_08.canonical import normalized_request
from glio_proteogen.modules.c27_complex_activity.m27_08_retirement import (
    M2708Service,
    RetirementAuthorizationError,
)


@pytest.mark.parametrize(
    "field", ["criteria", "migrations", "preserved_evidence", "communications", "source_artifacts"]
)
def test_empty_required_collections_reject(field: str) -> None:
    payload = build_request().model_dump(mode="json")
    payload[field] = []
    with pytest.raises(ValueError):
        M2708Service().validate_request(payload)


@pytest.mark.parametrize(
    "field", ["mass_spectrometry_proteome", "genome_transcriptome", "ptm_annotations"]
)
def test_scientific_input_is_opaque_reference_only(field: str) -> None:
    payload = build_request().model_dump(mode="json")
    payload[field]["media_type"] = "application/x-hostile-content"
    request = M2708Service().validate_request(payload)
    assert getattr(request, field).artifact_id.startswith("m2708.artifact")


def test_unsupported_upstream_media_abstains_without_scientific_traversal() -> None:
    request = build_request().model_copy(
        update={
            "source_artifacts": (
                build_request()
                .source_artifacts[0]
                .model_copy(update={"media_type": "application/json"}),
            )
            + build_request().source_artifacts[1:]
        }
    )
    with pytest.raises(ValueError, match="unsupported upstream"):
        M2708Service().execute(request)


def test_all_retirement_control_findings_are_emitted_together() -> None:
    request = build_request()
    bad = request.model_copy(
        update={
            "criteria": (request.criteria[0].model_copy(update={"satisfied": False}),),
            "migrations": (
                request.migrations[0].model_copy(update={"status": MigrationStatus.IN_PROGRESS}),
            ),
            "communications": (
                request.communications[0].model_copy(update={"acknowledged": False}),
            ),
            "archive": request.archive.model_copy(update={"status": ArchiveStatus.PRESERVED}),
        }
    )
    result = M2708Service().execute(bad)
    assert {finding.code.value for finding in result.findings} >= {
        "criterion_unsatisfied",
        "dependency_migration_incomplete",
        "communication_unacknowledged",
        "archive_unverified",
        "active_dependency",
    }


def test_empty_source_artifacts_fail_before_evaluation() -> None:
    request = build_request().model_copy(update={"source_artifacts": ()})
    with pytest.raises(RetirementAuthorizationError, match="source artifact"):
        M2708Service().execute(request)


def test_result_replay_detects_nested_request_mutation() -> None:
    result = M2708Service().execute(build_request())
    nested = result.model_copy(
        update={"request": result.request.model_copy(update={"request_id": "m2708.changed"})}
    )
    assert not M2708Service().verify(nested)


def test_canonical_dict_projection_is_supported() -> None:
    request = build_request()
    assert normalized_request(request.model_dump(mode="json"))["request_id"] == request.request_id


def test_preservation_and_archive_retrievability_closure() -> None:
    request = build_request()
    evidence = request.preserved_evidence[0].evidence
    with pytest.raises(ValueError):
        EvidencePreservation(
            preservation_id="m2708.invalid",
            artifact=request.preserved_evidence[0].artifact,
            retention_class="long-term",
            retrievable=False,
            evidence=evidence,
        )
    with pytest.raises(ValueError):
        LongTermArchive(
            archive_id="m2708.invalid",
            archive_reference="archive://invalid",
            retention_policy="indefinite",
            manifest=request.archive.manifest,
            status=ArchiveStatus.VERIFIED,
            retrievable=False,
            evidence=evidence,
        )


def test_unretrievable_archive_status_cannot_claim_retrieval() -> None:
    request = build_request()
    with pytest.raises(ValueError):
        LongTermArchive(
            archive_id="m2708.invalid",
            archive_reference="archive://invalid",
            retention_policy="indefinite",
            manifest=request.archive.manifest,
            status=ArchiveStatus.UNRETRIEVABLE,
            retrievable=True,
            evidence=request.archive.evidence,
        )


def test_duplicate_package_ids_are_rejected() -> None:
    request = build_request()
    with pytest.raises(ValueError):
        RetirementPackage(
            package_id="m2708.package.invalid",
            version="1.0.0",
            status=RetirementStatus.PROPOSED,
            criteria=(request.criteria[0], request.criteria[0]),
            migrations=request.migrations,
            preserved_evidence=request.preserved_evidence,
            communications=request.communications,
            archive=request.archive,
            configuration=request.configuration,
            evidence=request.criteria[0].evidence,
        )


def test_preflight_control_and_identity_firewalls() -> None:
    service = M2708Service()
    request = build_request()
    with pytest.raises(ValueError, match="context identity"):
        service.execute(request.model_copy(update={"request_id": "m2708.changed"}))
    unresolved = request.context.references.identity_lineage.model_copy(
        update={"state": "unresolved"}
    )
    with pytest.raises(ValueError, match="identity"):
        service.execute(
            request.model_copy(
                update={
                    "context": request.context.model_copy(
                        update={
                            "references": request.context.references.model_copy(
                                update={"identity_lineage": unresolved}
                            )
                        }
                    )
                }
            )
        )
    rejected = request.context.references.support.model_copy(update={"state": "rejected"})
    with pytest.raises(ValueError, match="accepted"):
        service.execute(
            request.model_copy(
                update={
                    "context": request.context.model_copy(
                        update={
                            "references": request.context.references.model_copy(
                                update={"support": rejected}
                            )
                        }
                    )
                }
            )
        )
