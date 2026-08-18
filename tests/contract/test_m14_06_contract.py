"""Lightweight contract and schema gates for provisional M14-06."""

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m14_06 import (
    M1406_OUTPUT_MEDIA_TYPE,
    PerturbationKind,
    PerturbationResponseStatus,
    PerturbationSpecification,
    SensitivityResponse,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import ArtifactReference, EvidenceReference

_SCHEMA_COUNT = 7


def _artifact(label: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1406": label}),
        media_type="application/json",
    )


def _evidence(label: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(label),
        role="counter_evidence",
        claim="Caller-declared counter-evidence for the bounded response.",
    )


def test_m1406_schemas_are_strict_and_explicitly_provisional() -> None:
    schemas = contract_json_schemas()

    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["$schema"].endswith("2020-12/schema") for schema in schemas.values())
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["pendingOwnerConfirmation"]
        for schema in schemas.values()
    )
    metadata = schemas["output"]["x-glio-contract"]
    assert metadata["outputMediaType"] == M1406_OUTPUT_MEDIA_TYPE
    assert metadata["parentTarget"] == "protein_subtype"
    assert metadata["boundedResponsesRequired"]
    assert metadata["assumptionsRequired"]
    assert metadata["alternativePriorsExplicit"]
    assert metadata["safeAbstentionRequired"]


def test_m1406_perturbation_and_bounded_response_invariants() -> None:
    perturbation = PerturbationSpecification(
        perturbation_id="scenario.prior",
        kind=PerturbationKind.ALTERNATIVE_PRIOR,
        target_ids=("protein.subtype",),
        parameter="prior_weight",
        baseline_value="0.25",
        perturbed_value="0.75",
        rationale="Stress the prior while preserving the declared target.",
        alternative_prior=_artifact("prior"),
    )
    assert perturbation.baseline_value != perturbation.perturbed_value

    response = SensitivityResponse(
        scenario_id="scenario.prior",
        status=PerturbationResponseStatus.BOUNDED,
        response_value=0.5,
        lower_bound=0.25,
        upper_bound=0.75,
        assumptions=("The perturbation remains within the supported envelope.",),
        counter_evidence=(_evidence("counter"),),
    )
    assert response.lower_bound <= response.response_value <= response.upper_bound

    with pytest.raises(ValueError, match="requires a prior artifact"):
        PerturbationSpecification(
            perturbation_id="scenario.invalid",
            kind=PerturbationKind.ALTERNATIVE_PRIOR,
            target_ids=("protein.subtype",),
            parameter="prior_weight",
            baseline_value="0.25",
            perturbed_value="0.75",
            rationale="Missing prior fixture.",
        )
