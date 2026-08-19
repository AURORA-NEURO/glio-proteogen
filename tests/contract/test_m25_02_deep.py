"""Deep M25-02 contract closure and hostile-input tests."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from glio_proteogen.contracts.m25_02 import (
    M2502_DOSSIER_SHA256,
    M2502_DOSSIER_SLICE,
    M2502_M2501_INPUT_MEDIA_TYPE,
    FixtureKind,
    GenerateProteotypeSyntheticTruthRequest,
    GenerationConfiguration,
    GenerationManifest,
    SyntheticTruthCase,
    SyntheticTruthCorpus,
    TruthRepresentation,
    canonical_request_digest,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import sha256_digest
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


def _artifact(label: str, *, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"m2502.artifact.{label}",
        version="1.0.0",
        digest="sha256:" + hashlib.sha256(label.encode()).hexdigest(),
        media_type=media_type,
    )


def _evidence(label: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(label),
        role="evidence",
        claim="Caller-declared synthetic truth evidence.",
    )


def _controls() -> ContextReferences:
    def decision(label: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"m2502.decision.{label}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(f"control-{label}"),
        )

    return ContextReferences(
        approved_configuration=decision("configuration"),
        identity_lineage=IdentityLineageReference(
            decision_id="m2502.decision.identity",
            state=IdentityLineageState.RESOLVED,
            policy_version="1.0.0",
            binding_digest=sha256_digest("identity"),
            evidence=_artifact("control-identity"),
        ),
        provenance=decision("provenance"),
        consent=ConsentReference(
            decision_id="m2502.decision.consent",
            state=ConsentState.GRANTED,
            policy_version="1.0.0",
            evidence=_artifact("control-consent"),
        ),
        quality=decision("quality"),
        support=decision("support"),
        intended_use=decision("intended-use"),
    )


def _configuration() -> GenerationConfiguration:
    return GenerationConfiguration(
        configuration_id="m2502.configuration.locked",
        version="1.0.0",
        generator_name="analytic synthetic truth generator",
        seed=42,
        requested_fixture_kinds=(FixtureKind.NORMAL, FixtureKind.ADVERSARIAL),
    )


def _request() -> GenerateProteotypeSyntheticTruthRequest:
    upstream = _artifact("m2501-upstream", media_type=M2502_M2501_INPUT_MEDIA_TYPE)
    source = (upstream, _artifact("source-proteome"))
    return GenerateProteotypeSyntheticTruthRequest(
        request_id="m2502.request.1",
        context=ExecutionContext(
            request_id="m2502.request.1",
            actor_id="m2502.actor",
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            references=_controls(),
        ),
        upstream_result=upstream,
        configuration=_configuration(),
        requested_case_count=2,
        source_artifacts=source,
    )


def _case(case_id: str) -> SyntheticTruthCase:
    return SyntheticTruthCase(
        case_id=case_id,
        fixture_kind=FixtureKind.NORMAL,
        representation=TruthRepresentation.ANALYTIC,
        seed=42,
        expected_features=("feature-a", "feature-b"),
        truth_values=("1.0", "2.0"),
        evidence=(_evidence(case_id),),
    )


def test_authority_and_schema_metadata_are_locked() -> None:
    schemas = cast("dict[str, dict[str, Any]]", contract_json_schemas())
    assert M2502_DOSSIER_SHA256.startswith("sha256:")
    assert M2502_DOSSIER_SLICE.endswith("8720-8760")
    assert all(
        schema["x-glio-contract"]["dossierSha256"] == M2502_DOSSIER_SHA256
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["dossierSlice"] == M2502_DOSSIER_SLICE
        for schema in schemas.values()
    )
    assert canonical_request_digest(_request()).startswith("sha256:")


def test_request_binds_context_upstream_and_unique_source_artifacts() -> None:
    request = _request()
    payload = request.model_dump(mode="python")
    payload["context"]["request_id"] = "m2502.forged"
    with pytest.raises(ValueError, match="request ID"):
        GenerateProteotypeSyntheticTruthRequest.model_validate(payload)

    payload = request.model_dump(mode="python")
    payload["source_artifacts"] = payload["source_artifacts"][1:]
    with pytest.raises(ValueError, match="bind the declared upstream"):
        GenerateProteotypeSyntheticTruthRequest.model_validate(payload)

    payload = request.model_dump(mode="python")
    payload["source_artifacts"] = (*request.source_artifacts, request.source_artifacts[0])
    with pytest.raises(ValueError, match="unique artifact"):
        GenerateProteotypeSyntheticTruthRequest.model_validate(payload)


def test_configuration_and_corpus_manifest_closure_are_explicit() -> None:
    with pytest.raises(ValueError, match="unique"):
        GenerationConfiguration(
            configuration_id="duplicate-kinds",
            version="1.0.0",
            generator_name="generator",
            seed=1,
            requested_fixture_kinds=(FixtureKind.NORMAL, FixtureKind.NORMAL),
        )

    case = _case("m2502.case.1")
    manifest = GenerationManifest(
        manifest_id="m2502.manifest",
        version="1.0.0",
        configuration=_configuration(),
        case_ids=(case.case_id,),
        reproducibility_digest=sha256_digest({"cases": (case,), "configuration": _configuration()}),
        fixture_summary=("normal",),
        evidence=(_evidence("manifest"),),
    )
    corpus = SyntheticTruthCorpus(
        corpus_id="m2502.corpus",
        version="1.0.0",
        cases=(case,),
        manifest=manifest,
        source_artifacts=(_artifact("m2501-upstream", media_type=M2502_M2501_INPUT_MEDIA_TYPE),),
        evidence=(_evidence("corpus"),),
    )
    assert corpus.manifest.case_ids == (case.case_id,)
    with pytest.raises(ValueError, match="enumerate"):
        SyntheticTruthCorpus(
            corpus_id=corpus.corpus_id,
            version=corpus.version,
            cases=(case,),
            manifest=manifest.model_copy(update={"case_ids": ("missing-case",)}),
            source_artifacts=corpus.source_artifacts,
            evidence=corpus.evidence,
        )
