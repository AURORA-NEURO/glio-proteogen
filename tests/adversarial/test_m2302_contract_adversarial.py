"""Adversarial contract, boundary, and replay-identity coverage for M23-02."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from glio_proteogen.contracts.m23_02 import (
    M2302_M2301_INPUT_MEDIA_TYPE,
    FixtureKind,
    GenerateVariantPeptideSyntheticTruthRequest,
    GenerationConfiguration,
    GenerationManifest,
    GenerationStatus,
    SyntheticTruthCase,
    SyntheticTruthCorpus,
    TruthRepresentation,
    VariantPeptideSyntheticTruthResult,
    canonical_request_digest,
    result_identifier,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m2302.{name}",
        version="1.0.0",
        digest=sha256_digest(f"m2302:{name}:{media_type}"),
        media_type=media_type,
    )


def _evidence(name: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(name), role="evidence", claim="M23-02 caller evidence."
    )


def _context(request_id: str = "request.m2302.synthetic") -> ExecutionContext:
    evidence = _artifact("control")
    accepted = UpstreamDecisionReference(
        decision_id="decision.m2302.accepted",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=evidence,
    )
    return ExecutionContext(
        request_id=request_id,
        actor_id="actor.m2302.synthetic",
        occurred_at=datetime(2026, 8, 16, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted,
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m2302.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("m2302.identity"),
                evidence=evidence,
            ),
            provenance=accepted,
            consent=ConsentReference(
                decision_id="decision.m2302.consent",
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
        configuration_id="configuration.m2302.synthetic",
        version="1.0.0",
        generator_name="m2302.synthetic.generator",
        seed=17,
        requested_fixture_kinds=tuple(FixtureKind),
        evidence=(_evidence("configuration"),),
    )


def _case(kind: FixtureKind, index: int) -> SyntheticTruthCase:
    return SyntheticTruthCase(
        case_id=f"case.m2302.{index}",
        fixture_kind=kind,
        representation=(
            TruthRepresentation.ANALYTIC
            if kind in {FixtureKind.NORMAL, FixtureKind.EDGE}
            else TruthRepresentation.SEMI_SYNTHETIC
        ),
        seed=index + 1,
        expected_features=("feature.a", "feature.b"),
        truth_values=("1.0", "2.0"),
        perturbations=(kind.value,),
        evidence=(_evidence(f"case-{index}"),),
    )


def _manifest(cases: tuple[SyntheticTruthCase, ...], version: str = "1.0.0") -> GenerationManifest:
    return GenerationManifest(
        manifest_id="manifest.m2302.synthetic",
        version=version,
        configuration=_configuration(),
        case_ids=tuple(item.case_id for item in cases),
        reproducibility_digest=sha256_digest("m2302.manifest"),
        fixture_summary=tuple(item.fixture_kind.value for item in cases),
        evidence=(_evidence("manifest"),),
    )


def _corpus() -> SyntheticTruthCorpus:
    cases = tuple(_case(kind, index) for index, kind in enumerate(FixtureKind))
    return SyntheticTruthCorpus(
        corpus_id="corpus.m2302.synthetic",
        version="1.0.0",
        cases=cases,
        manifest=_manifest(cases),
        source_artifacts=(_artifact("upstream", M2302_M2301_INPUT_MEDIA_TYPE), _artifact("source")),
        evidence=(_evidence("corpus"),),
    )


def _request() -> GenerateVariantPeptideSyntheticTruthRequest:
    upstream = _artifact("upstream", M2302_M2301_INPUT_MEDIA_TYPE)
    return GenerateVariantPeptideSyntheticTruthRequest(
        request_id="request.m2302.synthetic",
        context=_context(),
        upstream_result=upstream,
        configuration=_configuration(),
        requested_case_count=len(tuple(FixtureKind)),
        source_artifacts=(upstream, _artifact("source")),
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="M23-02 synthetic truth does not estimate scientific uncertainty.",
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=("Synthetic values are bounded by the locked caller seed.",),
    )


def _generated_result() -> VariantPeptideSyntheticTruthResult:
    request = _request()
    corpus = _corpus()
    payload: dict[str, Any] = {
        "output_type": "variant_peptide_synthetic_truth",
        "result_id": result_identifier(request),
        "result_version": "0.1.0-provisional",
        "request_digest": canonical_request_digest(request),
        "result_digest": "sha256:" + ("0" * 64),
        "request": request,
        "status": GenerationStatus.GENERATED,
        "corpus": corpus,
        "manifest": corpus.manifest,
        "findings": (),
        "abstention_reason": None,
        "parent_target": "variant peptide",
        "emits_parent": False,
        "support_decision": SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="m2302_synthetic_truth_supported",
            rationale="All five locked fixture kinds are represented.",
        ),
        "uncertainty": _uncertainty(),
        "provenance": ProvenanceRecord(
            activity_id="activity.m2302.synthetic",
            actor_id=request.context.actor_id,
            module_id="GLIO-PROTEOGEN-M23-02",
            module_version="0.1.0-provisional",
            generated_at=request.context.occurred_at,
            input_digests=(request.upstream_result.digest, _artifact("source").digest),
            configuration_digest=_artifact("configuration").digest,
            consent_decision_id=request.context.references.consent.decision_id,
            consent_state=request.context.references.consent.state,
            consent_policy_version=request.context.references.consent.policy_version,
            consent_evidence_digest=request.context.references.consent.evidence.digest,
            control_decisions=tuple(
                ControlDecisionRecord(
                    role=role,
                    decision_id=f"decision.m2302.{role.value}",
                    state=(
                        IdentityLineageState.RESOLVED.value
                        if role is ControlRole.IDENTITY_LINEAGE
                        else (
                            ConsentState.GRANTED.value
                            if role is ControlRole.CONSENT
                            else UpstreamDecisionState.ACCEPTED.value
                        )
                    ),
                    policy_version="1.0.0",
                    evidence_digest=_artifact("control").digest,
                    subject_digest=(
                        sha256_digest("m2302.identity")
                        if role is ControlRole.IDENTITY_LINEAGE
                        else None
                    ),
                )
                for role in ControlRole
            ),
        ),
        "evidence": (_evidence("result"),),
        "limitations": (
            Limitation(code="m2302_provisional", statement="The M23-02 ABI is provisional."),
        ),
        "human_review_required": False,
    }
    constructed = VariantPeptideSyntheticTruthResult.model_construct(**payload)
    payload["result_digest"] = result_payload_digest(constructed)
    return VariantPeptideSyntheticTruthResult.model_validate(payload)


def test_configuration_case_and_manifest_invariants_are_fail_closed() -> None:
    config = _configuration().model_dump(mode="python")
    config["requested_fixture_kinds"] = tuple(FixtureKind)[:-1]
    with pytest.raises(ValueError, match="must request"):
        GenerationConfiguration.model_validate(config)
    config["requested_fixture_kinds"] = (
        FixtureKind.NORMAL,
        FixtureKind.NORMAL,
        FixtureKind.EDGE,
        FixtureKind.MISSING,
        FixtureKind.SHIFTED,
    )
    with pytest.raises(ValueError, match="must be unique"):
        GenerationConfiguration.model_validate(config)
    duplicate_case = _case(FixtureKind.NORMAL, 0).model_dump(mode="python")
    duplicate_case["truth_values"] = ("1.0",)
    with pytest.raises(ValueError, match="equal dimensions"):
        SyntheticTruthCase.model_validate(duplicate_case)
    cases = tuple(_case(kind, index) for index, kind in enumerate(FixtureKind))
    manifest = _manifest(cases).model_dump(mode="python")
    manifest["case_ids"] = (*manifest["case_ids"][:-1], manifest["case_ids"][0])
    with pytest.raises(ValueError, match="manifest case ids"):
        GenerationManifest.model_validate(manifest)
    manifest = _manifest(cases).model_dump(mode="python")
    manifest["reproducibility_digest"] = "sha256:" + ("0" * 64)
    with pytest.raises(ValueError, match="cannot be zero"):
        GenerationManifest.model_validate(manifest)
    duplicate_cases = list(cases)
    duplicate_cases[1] = duplicate_cases[1].model_copy(
        update={"case_id": duplicate_cases[0].case_id}
    )
    duplicate_corpus = _corpus().model_dump(mode="python")
    duplicate_corpus["cases"] = tuple(duplicate_cases)
    with pytest.raises(ValueError, match="corpus case ids must be unique"):
        SyntheticTruthCorpus.model_validate(duplicate_corpus)


def test_corpus_closure_rejects_manifest_version_and_source_tampering() -> None:
    corpus = _corpus()
    changed = corpus.model_dump(mode="python")
    changed["manifest"] = _manifest(corpus.cases, version="2.0.0")
    with pytest.raises(ValueError, match="versions must match"):
        SyntheticTruthCorpus.model_validate(changed)
    changed = corpus.model_dump(mode="python")
    changed["source_artifacts"] = (corpus.source_artifacts[0],) * 2
    with pytest.raises(ValueError, match="source artifacts must be unique"):
        SyntheticTruthCorpus.model_validate(changed)
    changed = corpus.model_dump(mode="python")
    changed["manifest"] = _manifest(corpus.cases[:-1])
    with pytest.raises(ValueError, match="every corpus case"):
        SyntheticTruthCorpus.model_validate(changed)


def test_request_media_context_and_upstream_retention_are_closed() -> None:
    request = _request()
    changed = request.model_dump(mode="python")
    changed["context"] = _context("request.m2302.other")
    with pytest.raises(ValueError, match="context must bind"):
        GenerateVariantPeptideSyntheticTruthRequest.model_validate(changed)
    changed = request.model_dump(mode="python")
    changed["upstream_result"] = _artifact("wrong")
    with pytest.raises(ValueError, match="M23-01"):
        GenerateVariantPeptideSyntheticTruthRequest.model_validate(changed)
    changed = request.model_dump(mode="python")
    changed["source_artifacts"] = (_artifact("source-only"),)
    with pytest.raises(ValueError, match="retain M23-01"):
        GenerateVariantPeptideSyntheticTruthRequest.model_validate(changed)
    changed = request.model_dump(mode="python")
    changed["source_artifacts"] = (request.source_artifacts[0],) * 2
    with pytest.raises(ValueError, match="source artifacts must be unique"):
        GenerateVariantPeptideSyntheticTruthRequest.model_validate(changed)


def test_result_identity_digest_and_safe_status_are_replay_closed() -> None:
    result = _generated_result()
    assert result.result_id == result_identifier(result.request)
    assert result.result_digest == result_payload_digest(result)
    changed = result.__dict__.copy()
    changed["result_id"] = "result." + "f" * 64
    with pytest.raises(ValueError, match="identifier must be derived"):
        VariantPeptideSyntheticTruthResult.model_validate(changed)
    changed = result.__dict__.copy()
    changed["request_digest"] = "sha256:" + "f" * 64
    with pytest.raises(ValueError, match="exact request"):
        VariantPeptideSyntheticTruthResult.model_validate(changed)
    changed = result.__dict__.copy()
    changed["support_decision"] = SupportDecision(
        status=SupportStatus.UNSUPPORTED,
        reason_code="m2302_unsupported",
        rationale="Unsupported fixture.",
    )
    changed["status"] = GenerationStatus.ABSTAINED
    changed["corpus"] = None
    changed["manifest"] = None
    changed["abstention_reason"] = "unsupported fixture"
    changed["human_review_required"] = False
    changed["result_digest"] = result_payload_digest(changed)
    with pytest.raises(ValueError, match="safe status"):
        VariantPeptideSyntheticTruthResult.model_validate(changed)

    generated_without_corpus = result.__dict__.copy()
    generated_without_corpus["corpus"] = None
    generated_without_corpus["manifest"] = None
    with pytest.raises(ValueError, match="supported corpus and manifest"):
        VariantPeptideSyntheticTruthResult.model_validate(generated_without_corpus)

    abstained = result.__dict__.copy()
    abstained.update(
        {
            "status": GenerationStatus.ABSTAINED,
            "corpus": None,
            "manifest": None,
            "abstention_reason": "fixture support requires review",
            "support_decision": SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="m2302_review_required",
                rationale="The caller-declared support decision requires manual review.",
            ),
            "human_review_required": True,
        }
    )
    abstained["result_digest"] = result_payload_digest(
        VariantPeptideSyntheticTruthResult.model_construct(**abstained)
    )
    validated = VariantPeptideSyntheticTruthResult.model_validate(abstained)
    assert validated.status is GenerationStatus.ABSTAINED
