"""Lightweight contract and schema gates for provisional M15-04."""

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m15_04 import (
    M1504_OUTPUT_MEDIA_TYPE,
    MechanismEstimate,
    MechanismEstimateKind,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import ArtifactReference, EvidenceReference

_SCHEMA_COUNT = 5


def _artifact(label: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1504": label}),
        media_type="application/json",
    )


def _evidence(label: str, role: str = "evidence") -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(label),
        role=role,
        claim=f"Evidence claim for {label}.",
    )


def test_m1504_schemas_are_strict_and_explicitly_provisional() -> None:
    schemas = contract_json_schemas()

    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["$schema"].endswith("2020-12/schema") for schema in schemas.values())
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    metadata = schemas["output"]["x-glio-contract"]
    assert metadata["outputMediaType"] == M1504_OUTPUT_MEDIA_TYPE
    assert metadata["parentTarget"] == "complex_activity"
    assert metadata["counterEvidenceRequired"]
    assert metadata["assumptionsAndAlternativesRequired"]
    assert metadata["explicitAbstentionRequired"]


def test_m1504_posterior_requires_bounds_assumptions_alternatives_and_counter_evidence() -> None:
    estimate = MechanismEstimate(
        estimate_id="estimate.complex",
        mechanism_id="mechanism.complex",
        label="Complex mechanism posterior",
        kind=MechanismEstimateKind.POSTERIOR,
        posterior_probability=0.6,
        lower_bound=0.4,
        upper_bound=0.8,
        assumptions=("The structure-aware model is in domain.",),
        alternatives=("A competing stoichiometry remains possible.",),
        counter_evidence=(_evidence("counter", "counter_evidence"),),
    )
    assert estimate.lower_bound <= estimate.posterior_probability <= estimate.upper_bound

    with pytest.raises(ValueError, match="posterior estimate requires"):
        MechanismEstimate(
            estimate_id="estimate.invalid",
            mechanism_id="mechanism.invalid",
            label="Incomplete posterior",
            kind=MechanismEstimateKind.POSTERIOR,
            assumptions=("Assumption.",),
            alternatives=("Alternative.",),
            counter_evidence=(_evidence("invalid", "counter_evidence"),),
        )
