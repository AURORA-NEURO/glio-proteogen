"""Adversarial closure tests for provisional M20-02 alignment contracts."""

from __future__ import annotations

from hashlib import sha256

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m20_02 import (
    AlignedEvidenceBundle,
    AlignmentConfiguration,
    AlignmentDimension,
    AlignmentObservation,
    AlignmentObservationStatus,
    DiscrepancyMapEntry,
    DiscrepancySeverity,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    EvidenceReference,
)


def _artifact(name: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{name}",
        version="1.0.0",
        digest=f"sha256:{sha256(name.encode()).hexdigest()}",
        media_type="application/json",
    )


def _evidence(name: str) -> EvidenceReference:
    return EvidenceReference(reference=_artifact(name), role="evidence", claim="declared evidence")


def _configuration(dimensions: tuple[AlignmentDimension, ...]) -> AlignmentConfiguration:
    return AlignmentConfiguration(
        configuration_id="configuration.m2002.locked",
        version="1.0.0",
        required_dimensions=dimensions,
        evidence=(_evidence("e"),),
    )


def _observation(dimension: AlignmentDimension) -> AlignmentObservation:
    return AlignmentObservation(
        observation_id=f"observation.{dimension.value}",
        dimension=dimension,
        source_ids=("artifact.source-a", "artifact.source-b"),
        reference_value="declared-reference",
        observed_values=("value-a", "value-b"),
        status=AlignmentObservationStatus.ALIGNED,
        rationale="two caller-declared values are aligned under the locked rule",
        evidence=(_evidence(f"x{dimension.value[0]}"),),
    )


def test_configuration_rejects_duplicate_dimensions() -> None:
    dimensions = (*tuple(AlignmentDimension)[:-1], AlignmentDimension.SAMPLE)
    with pytest.raises(ValidationError, match="dimensions must be unique"):
        _configuration(dimensions)


def test_configuration_rejects_missing_dimension() -> None:
    dimensions = (*tuple(AlignmentDimension)[:-1], AlignmentDimension.SAMPLE)
    with pytest.raises(ValidationError, match="dimensions must be unique"):
        _configuration(dimensions)


def test_discrepancy_rejects_duplicate_sources() -> None:
    with pytest.raises(ValidationError, match="source ids must be unique"):
        DiscrepancyMapEntry(
            discrepancy_id="discrepancy.duplicate",
            dimension=AlignmentDimension.REFERENCE,
            source_ids=("artifact.source-a", "artifact.source-a"),
            severity=DiscrepancySeverity.ROUTINE,
            description="duplicate source declaration",
            evidence=(_evidence("duplicate-source"),),
        )


def test_bundle_requires_all_seven_alignment_dimensions() -> None:
    source_artifacts = (_artifact("source-a"), _artifact("source-b"))
    observations = tuple(_observation(dimension) for dimension in tuple(AlignmentDimension)[:-1])
    with pytest.raises(ValidationError, match="cover all seven dimensions"):
        AlignedEvidenceBundle(
            bundle_id="bundle.m2002.incomplete",
            version="1.0.0",
            source_artifacts=source_artifacts,
            observations=observations,
            configuration=_configuration(tuple(AlignmentDimension)),
            evidence=(_evidence("bundle"),),
        )


def test_critical_discrepancy_requires_resolution() -> None:
    source_artifacts = (_artifact("source-a"), _artifact("source-b"))
    observations = tuple(_observation(dimension) for dimension in AlignmentDimension)
    discrepancy = DiscrepancyMapEntry(
        discrepancy_id="discrepancy.critical",
        dimension=AlignmentDimension.REFERENCE,
        source_ids=("artifact.source-a", "artifact.source-b"),
        severity=DiscrepancySeverity.CRITICAL,
        description="reference versions disagree",
        evidence=(_evidence("discrepancy"),),
    )
    with pytest.raises(ValidationError, match="critical discrepancies require"):
        AlignedEvidenceBundle(
            bundle_id="bundle.m2002.critical",
            version="1.0.0",
            source_artifacts=source_artifacts,
            observations=observations,
            discrepancies=(discrepancy,),
            configuration=_configuration(tuple(AlignmentDimension)),
            evidence=(_evidence("bundle"),),
        )


def test_bundle_rejects_duplicate_ids_and_unknown_references() -> None:
    source_artifacts = (_artifact("source-a"), _artifact("source-b"))
    observations = tuple(_observation(dimension) for dimension in AlignmentDimension)
    duplicate_observation = observations[0].model_copy(
        update={"observation_id": observations[1].observation_id}
    )
    with pytest.raises(ValidationError, match="observation ids must be unique"):
        AlignedEvidenceBundle(
            bundle_id="bundle.m2002.duplicate-observation",
            version="1.0.0",
            source_artifacts=source_artifacts,
            observations=(duplicate_observation, *observations[1:]),
            configuration=_configuration(tuple(AlignmentDimension)),
            evidence=(_evidence("bundle-duplicate-observation"),),
        )
    unknown = observations[0].model_copy(
        update={"source_ids": ("artifact.unknown", "artifact.source-b")}
    )
    with pytest.raises(ValidationError, match="unknown source artifact"):
        AlignedEvidenceBundle(
            bundle_id="bundle.m2002.unknown-observation",
            version="1.0.0",
            source_artifacts=source_artifacts,
            observations=(unknown, *observations[1:]),
            configuration=_configuration(tuple(AlignmentDimension)),
            evidence=(_evidence("bundle-unknown-observation"),),
        )
