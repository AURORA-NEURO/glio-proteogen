"""Adversarial contract and replay-identity coverage for provisional M22-02."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m22_02 import (
    M2202_DOSSIER_SHA256,
    M2202_DOSSIER_SLICE,
    M2202_M2201_INPUT_MEDIA_TYPE,
    M2202_MODULE_ID,
    FixtureKind,
    GenerateProteinRnaDiscordanceSyntheticTruthRequest,
    GenerationConfiguration,
    GenerationManifest,
    TruthRepresentation,
    canonical_request_digest,
    contract_json_schemas,
    result_identifier,
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

_SCHEMA_COUNT = 7


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="0.1.0",
        digest="sha256:" + hashlib.sha256(name.encode()).hexdigest(),
        media_type=media_type,
    )


def _context(request_id: str = "m2202.request") -> ExecutionContext:
    evidence = _artifact("m2202.control.evidence")
    accepted = UpstreamDecisionReference(
        decision_id="m2202.accepted",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=evidence,
    )
    return ExecutionContext(
        request_id=request_id,
        actor_id="m2202.actor",
        occurred_at=datetime(2026, 8, 16, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted,
            identity_lineage=IdentityLineageReference(
                decision_id="m2202.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest="sha256:" + "b" * 64,
                evidence=evidence,
            ),
            provenance=accepted,
            consent=ConsentReference(
                decision_id="m2202.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=evidence,
            ),
            quality=accepted,
            support=accepted,
            intended_use=accepted,
        ),
    )


def _configuration() -> GenerationConfiguration:
    return GenerationConfiguration(
        configuration_id="m2202.configuration",
        version="1.0.0",
        generator_name="deterministic-fixture-generator",
        seed=7,
        requested_fixture_kinds=(FixtureKind.NORMAL, FixtureKind.SHIFTED),
    )


def _evidence(name: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(name),
        role="evidence",
        claim="Caller-declared synthetic truth contract evidence.",
    )


def _request() -> GenerateProteinRnaDiscordanceSyntheticTruthRequest:
    upstream = _artifact("m2201.reference.truth", M2202_M2201_INPUT_MEDIA_TYPE)
    return GenerateProteinRnaDiscordanceSyntheticTruthRequest(
        request_id="m2202.request",
        context=_context(),
        upstream_result=upstream,
        configuration=_configuration(),
        requested_case_count=2,
        source_artifacts=(upstream, _artifact("m2202.generator.policy")),
    )


def test_schema_binds_authority_and_safe_boundaries() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    for schema in schemas.values():
        metadata = schema["x-glio-contract"]
        assert metadata["moduleId"] == M2202_MODULE_ID
        assert metadata["dossierSha256"] == M2202_DOSSIER_SHA256
        assert metadata["dossierSlice"] == M2202_DOSSIER_SLICE
        assert metadata["unsupportedToNegative"] is False
        assert metadata["explicitAbstentionRequired"] is True
        assert metadata["analyticallyKnownFixturesRequired"] is True
        assert metadata["semiSyntheticFixturesRequired"] is True


def test_request_requires_context_and_upstream_source_closure() -> None:
    request = _request()
    assert canonical_request_digest(request) == canonical_request_digest(
        request.model_dump(mode="json")
    )
    assert result_identifier(request).startswith("m2202.result.")

    payload = request.model_dump(mode="python")
    payload["context"]["request_id"] = "m2202.other"
    with pytest.raises(ValidationError, match="context request id"):
        GenerateProteinRnaDiscordanceSyntheticTruthRequest(**payload)

    payload = request.model_dump(mode="python")
    payload["source_artifacts"] = (payload["source_artifacts"][1],)
    with pytest.raises(ValidationError, match="include the M22-01 result"):
        GenerateProteinRnaDiscordanceSyntheticTruthRequest(**payload)

    payload = request.model_dump(mode="python")
    payload["source_artifacts"] = payload["source_artifacts"] + (payload["source_artifacts"][0],)
    with pytest.raises(ValidationError, match="source artifacts must be unique"):
        GenerateProteinRnaDiscordanceSyntheticTruthRequest(**payload)


def test_configuration_and_manifest_ids_are_unique() -> None:
    with pytest.raises(ValidationError, match="fixture kinds must be unique"):
        GenerationConfiguration(
            configuration_id="m2202.configuration",
            version="1.0.0",
            generator_name="deterministic-fixture-generator",
            seed=7,
            requested_fixture_kinds=(FixtureKind.NORMAL, FixtureKind.NORMAL),
        )

    configuration = _configuration()
    with pytest.raises(ValidationError, match="manifest case ids must be unique"):
        GenerationManifest(
            manifest_id="m2202.manifest",
            version="1.0.0",
            configuration=configuration,
            case_ids=("m2202.case", "m2202.case"),
            reproducibility_digest="sha256:" + "a" * 64,
            fixture_summary=("normal",),
            evidence=(_evidence("m2202.manifest.evidence"),),
        )


def test_truth_representation_remains_explicit() -> None:
    assert TruthRepresentation.ANALYTIC.value == "analytic"
    assert TruthRepresentation.SEMI_SYNTHETIC.value == "semi_synthetic"
