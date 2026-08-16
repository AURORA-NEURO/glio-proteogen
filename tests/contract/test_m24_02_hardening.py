"""Adversarial contract and replay-identity coverage for provisional M24-02."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import cast

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m24_02 import (
    M2402_DOSSIER_SHA256,
    M2402_DOSSIER_SLICE,
    M2402_M2401_INPUT_MEDIA_TYPE,
    M2402_MODULE_ID,
    FixtureKind,
    GenerateBiomarkerPanelSyntheticTruthRequest,
    GenerationConfiguration,
    GenerationManifest,
    SyntheticTruthCase,
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


def _evidence(name: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(name),
        role="evidence",
        claim="Caller-declared M24-02 synthetic truth evidence.",
    )


def _context(request_id: str = "m2402.request") -> ExecutionContext:
    evidence = _artifact("m2402.control.evidence")
    accepted = UpstreamDecisionReference(
        decision_id="m2402.accepted",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=evidence,
    )
    return ExecutionContext(
        request_id=request_id,
        actor_id="m2402.actor",
        occurred_at=datetime(2026, 8, 16, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted,
            identity_lineage=IdentityLineageReference(
                decision_id="m2402.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest="sha256:" + "b" * 64,
                evidence=evidence,
            ),
            provenance=accepted,
            consent=ConsentReference(
                decision_id="m2402.consent",
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
        configuration_id="m2402.configuration",
        version="1.0.0",
        generator_name="deterministic-fixture-generator",
        seed=7,
        requested_fixture_kinds=(FixtureKind.NORMAL, FixtureKind.SHIFTED),
    )


def _case(case_id: str = "m2402.case") -> SyntheticTruthCase:
    return SyntheticTruthCase(
        case_id=case_id,
        fixture_kind=FixtureKind.NORMAL,
        representation=TruthRepresentation.ANALYTIC,
        seed=7,
        expected_features=("protein_a", "protein_b"),
        truth_values=("1.0", "2.0"),
        evidence=(_evidence(case_id + ".evidence"),),
    )


def _request() -> GenerateBiomarkerPanelSyntheticTruthRequest:
    upstream = _artifact("m2401.sensitivity", M2402_M2401_INPUT_MEDIA_TYPE)
    return GenerateBiomarkerPanelSyntheticTruthRequest(
        request_id="m2402.request",
        context=_context(),
        upstream_result=upstream,
        configuration=_configuration(),
        requested_case_count=2,
        source_artifacts=(upstream, _artifact("m2402.generator.policy")),
    )


def test_schema_binds_authority_and_safe_boundaries() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    for schema in schemas.values():
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert metadata["moduleId"] == M2402_MODULE_ID
        assert metadata["authoritySha256"] == M2402_DOSSIER_SHA256
        assert metadata["authoritySlice"] == M2402_DOSSIER_SLICE
        assert metadata["unsupportedToNegative"] is False
        assert metadata["explicitAbstentionRequired"] is True
        assert metadata["analyticallyKnownFixturesRequired"] is True
        assert metadata["semiSyntheticFixturesRequired"] is True


def test_request_requires_context_and_upstream_source_closure() -> None:
    request = _request()
    assert canonical_request_digest(request) == canonical_request_digest(
        request.model_dump(mode="json")
    )
    assert result_identifier(request).startswith("result.")
    with pytest.raises(ValidationError, match="context request id"):
        GenerateBiomarkerPanelSyntheticTruthRequest.model_validate(
            request.model_dump(mode="python") | {"context": _context("m2402.other")},
            strict=True,
        )
    with pytest.raises(ValidationError, match="include the upstream"):
        GenerateBiomarkerPanelSyntheticTruthRequest.model_validate(
            request.model_dump(mode="python")
            | {"source_artifacts": (request.source_artifacts[1],)},
            strict=True,
        )
    with pytest.raises(ValidationError, match="source artifact ids"):
        GenerateBiomarkerPanelSyntheticTruthRequest.model_validate(
            request.model_dump(mode="python")
            | {"source_artifacts": (request.source_artifacts[0],) * 2},
            strict=True,
        )


def test_configuration_and_manifest_ids_are_unique() -> None:
    with pytest.raises(ValidationError, match="fixture kinds must be unique"):
        GenerationConfiguration(
            configuration_id="m2402.configuration",
            version="1.0.0",
            generator_name="deterministic-fixture-generator",
            seed=7,
            requested_fixture_kinds=(FixtureKind.NORMAL, FixtureKind.NORMAL),
        )
    configuration = _configuration()
    with pytest.raises(ValidationError, match="manifest case ids must be unique"):
        GenerationManifest(
            manifest_id="m2402.manifest",
            version="1.0.0",
            configuration=configuration,
            case_ids=("m2402.case", "m2402.case"),
            reproducibility_digest="sha256:" + "a" * 64,
            fixture_summary=("normal",),
            evidence=(_evidence("m2402.manifest.evidence"),),
        )


def test_case_truth_shape_and_representation_are_explicit() -> None:
    assert TruthRepresentation.ANALYTIC.value == "analytic"
    assert TruthRepresentation.SEMI_SYNTHETIC.value == "semi_synthetic"
    with pytest.raises(ValidationError, match="equal length"):
        SyntheticTruthCase.model_validate(
            _case().model_dump(mode="python") | {"truth_values": ("1.0",)}, strict=True
        )
