"""Lightweight contract and schema gates for provisional M16-02."""

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m16_02 import (
    M1602_OUTPUT_MEDIA_TYPE,
    AlignedEvidenceBundle,
    AlignmentConfiguration,
    AlignmentDimension,
    AlignmentLink,
    AlignmentLinkStatus,
    DiscrepancyRecord,
    DiscrepancyResolutionStatus,
    DiscrepancySeverity,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import ArtifactReference

_SCHEMA_COUNT = 7


def _artifact(label: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1602": label}),
        media_type="application/json",
    )


def test_m1602_schemas_are_strict_and_explicitly_provisional() -> None:
    schemas = contract_json_schemas()

    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["$schema"].endswith("2020-12/schema") for schema in schemas.values())
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    metadata = schemas["output"]["x-glio-contract"]
    assert metadata["outputMediaType"] == M1602_OUTPUT_MEDIA_TYPE
    assert metadata["parentTarget"] == "protein_rna_discordance"
    assert metadata["conflictDetectionRequired"]
    assert metadata["discrepanciesRemainExplicit"]
    assert metadata["humanReviewForCriticalDiscrepancy"]
    assert metadata["explicitAbstentionRequired"]


def test_m1602_alignment_bundle_keeps_critical_discrepancies_reviewable() -> None:
    link = AlignmentLink(
        link_id="link.sample",
        dimensions=(AlignmentDimension.SAMPLE, AlignmentDimension.MODALITY),
        source_artifacts=(_artifact("proteome"), _artifact("transcriptome")),
        canonical_key="subject-1:sample-a",
        observed_values=("sample-a", "sample-a"),
        status=AlignmentLinkStatus.ALIGNED,
    )
    discrepancy = DiscrepancyRecord(
        discrepancy_id="discrepancy.time",
        dimensions=(AlignmentDimension.TIME,),
        source_link_ids=(link.link_id,),
        description="Collection time differs across source records.",
        severity=DiscrepancySeverity.CRITICAL,
        resolution_status=DiscrepancyResolutionStatus.OPEN,
    )
    bundle = AlignedEvidenceBundle(
        bundle_id="bundle.sample",
        version="1.0.0",
        links=(link,),
        discrepancies=(discrepancy,),
        configuration=AlignmentConfiguration(
            configuration_id="config.alignment",
            version="1.0.0",
            reference_artifact=_artifact("reference"),
            enabled_dimensions=(AlignmentDimension.SAMPLE, AlignmentDimension.TIME),
            conflict_policy="critical discrepancies require signed review",
        ),
    )
    assert bundle.discrepancies[0].resolution_status is DiscrepancyResolutionStatus.OPEN

    with pytest.raises(ValueError, match="resolved discrepancy requires"):
        DiscrepancyRecord(
            discrepancy_id="discrepancy.invalid",
            dimensions=(AlignmentDimension.TIME,),
            source_link_ids=(link.link_id,),
            description="Missing resolution fixture.",
            severity=DiscrepancySeverity.CRITICAL,
            resolution_status=DiscrepancyResolutionStatus.RESOLVED,
        )
