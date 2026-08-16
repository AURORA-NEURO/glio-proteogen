"""Adversarial contract and replay coverage for provisional M22-01."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m22_01 import (
    M2201_M2108_INPUT_MEDIA_TYPE,
    M2201_MODULE_ID,
    AdjudicationRecord,
    AdjudicationStatus,
    BenchmarkConfiguration,
    CurateProteinRnaDiscordanceReferenceTruthRequest,
    CurationFinding,
    CurationFindingCode,
    CurationStatus,
    EndpointDefinition,
    InclusionDecision,
    ProteinRnaDiscordanceReferenceTruthResult,
    ReferenceEntry,
    ReferenceKind,
    ReferenceTruthPackage,
    canonical_request_digest,
    reference_truth_package_digest,
    result_identifier,
    result_payload_digest,
)
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
        artifact_id=name,
        version="0.1.0",
        digest="sha256:" + hashlib.sha256(name.encode()).hexdigest(),
        media_type=media_type,
    )


def _evidence(name: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(name),
        role="evidence",
        claim="Caller-declared reference truth evidence.",
    )


def _context(request_id: str = "m2201.request") -> ExecutionContext:
    artifact = _artifact("m2201.control.evidence")
    accepted = UpstreamDecisionReference(
        decision_id="m2201.accepted",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=artifact,
    )
    return ExecutionContext(
        request_id=request_id,
        actor_id="m2201.actor",
        occurred_at=datetime(2026, 8, 16, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted,
            identity_lineage=IdentityLineageReference(
                decision_id="m2201.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest="sha256:" + "b" * 64,
                evidence=artifact,
            ),
            provenance=accepted,
            consent=ConsentReference(
                decision_id="m2201.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=artifact,
            ),
            quality=accepted,
            support=accepted,
            intended_use=accepted,
        ),
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="No calibrated reference-truth uncertainty is claimed by this provisional ABI.",
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
    )


def _entry(identifier: str, kind: ReferenceKind) -> ReferenceEntry:
    return ReferenceEntry(
        reference_id=identifier,
        kind=kind,
        artifact=_artifact(identifier + ".artifact"),
        expected_label="declared reference label",
        inclusion_reason="declared benchmark inclusion reason",
        provenance_artifact=_artifact(identifier + ".provenance"),
        challenge_set=kind is ReferenceKind.CHALLENGE_SET,
        uncertainty=_uncertainty(),
        evidence=(_evidence(identifier + ".evidence"),),
    )


def _endpoint() -> EndpointDefinition:
    return EndpointDefinition(
        endpoint_id="m2201.endpoint",
        name="protein-RNA discordance reference endpoint",
        definition="Caller-declared discordance definition.",
        metric="discordance_rate",
        acceptance_tolerance="Within the declared locked tolerance.",
        evidence=(_evidence("m2201.endpoint.evidence"),),
    )


def _configuration() -> BenchmarkConfiguration:
    return BenchmarkConfiguration(
        configuration_id="m2201.configuration",
        version="1.0.0",
        evidence=(_evidence("m2201.configuration.evidence"),),
    )


def _package() -> ReferenceTruthPackage:
    references = (
        _entry("m2201.calibrator", ReferenceKind.CALIBRATOR),
        _entry("m2201.challenge", ReferenceKind.CHALLENGE_SET),
    )
    controls = (_entry("m2201.positive", ReferenceKind.POSITIVE_CONTROL),)
    all_ids = ("m2201.calibrator", "m2201.challenge", "m2201.positive")
    payload: dict[str, Any] = {
        "package_id": "m2201.package",
        "version": "1.0.0",
        "endpoint": _endpoint(),
        "references": references,
        "controls": controls,
        "inclusions": tuple(
            InclusionDecision(
                reference_id=identifier,
                included=True,
                rationale="included under the declared curation policy",
                leakage_audit="no benchmark leakage declared",
                evidence=(_evidence(identifier + ".inclusion"),),
            )
            for identifier in all_ids
        ),
        "adjudications": tuple(
            AdjudicationRecord(
                reference_id=identifier,
                status=AdjudicationStatus.LOCKED,
                reviewer_tokens=("reviewer-a", "reviewer-b"),
                agreement_statement="Reviewers agree on the declared label.",
                evidence=(_evidence(identifier + ".adjudication"),),
            )
            for identifier in all_ids
        ),
        "challenge_set_ids": ("m2201.challenge",),
        "configuration": _configuration(),
        "lock_digest": "sha256:" + "0" * 64,
        "evidence": (_evidence("m2201.package.evidence"),),
    }
    provisional = ReferenceTruthPackage.model_construct(**payload)
    payload["lock_digest"] = reference_truth_package_digest(provisional)
    return ReferenceTruthPackage(**payload)


def _request() -> CurateProteinRnaDiscordanceReferenceTruthRequest:
    upstream = _artifact("m2108.evidence.gate", M2201_M2108_INPUT_MEDIA_TYPE)
    references = (
        _entry("m2201.calibrator", ReferenceKind.CALIBRATOR),
        _entry("m2201.challenge", ReferenceKind.CHALLENGE_SET),
    )
    controls = (_entry("m2201.positive", ReferenceKind.POSITIVE_CONTROL),)
    all_ids = ("m2201.calibrator", "m2201.challenge", "m2201.positive")
    return CurateProteinRnaDiscordanceReferenceTruthRequest(
        request_id="m2201.request",
        context=_context(),
        upstream_result=upstream,
        endpoint=_endpoint(),
        references=references,
        controls=controls,
        inclusions=tuple(
            InclusionDecision(
                reference_id=identifier,
                included=True,
                rationale="included under the declared curation policy",
                leakage_audit="no benchmark leakage declared",
                evidence=(_evidence(identifier + ".inclusion"),),
            )
            for identifier in all_ids
        ),
        adjudications=tuple(
            AdjudicationRecord(
                reference_id=identifier,
                status=AdjudicationStatus.LOCKED,
                reviewer_tokens=("reviewer-a", "reviewer-b"),
                agreement_statement="Reviewers agree on the declared label.",
                evidence=(_evidence(identifier + ".adjudication"),),
            )
            for identifier in all_ids
        ),
        configuration=_configuration(),
        challenge_set_ids=("m2201.challenge",),
        source_artifacts=(upstream, _artifact("m2201.reference.material")),
    )


def _provenance(request: CurateProteinRnaDiscordanceReferenceTruthRequest) -> ProvenanceRecord:
    artifact = _artifact("m2201.control.evidence")
    decisions = tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=f"m2201.decision.{role.value}",
            state=(
                "resolved"
                if role is ControlRole.IDENTITY_LINEAGE
                else "granted"
                if role is ControlRole.CONSENT
                else "accepted"
            ),
            policy_version="1.0.0",
            evidence_digest=artifact.digest,
            subject_digest="sha256:" + "b" * 64 if role is ControlRole.IDENTITY_LINEAGE else None,
        )
        for role in ControlRole
    )
    return ProvenanceRecord(
        activity_id="m2201.activity",
        actor_id=request.context.actor_id,
        module_id=M2201_MODULE_ID,
        module_version="0.1.0-provisional",
        generated_at=request.context.occurred_at,
        input_digests=tuple(artifact.digest for artifact in request.source_artifacts),
        configuration_digest=canonical_request_digest(request.configuration),
        consent_decision_id="m2201.consent",
        consent_state=ConsentState.GRANTED,
        consent_policy_version="1.0.0",
        consent_evidence_digest=artifact.digest,
        control_decisions=decisions,
    )


def _result(
    request: CurateProteinRnaDiscordanceReferenceTruthRequest,
) -> ProteinRnaDiscordanceReferenceTruthResult:
    payload: dict[str, Any] = {
        "result_id": result_identifier(request),
        "result_version": "0.1.0-provisional",
        "request_digest": canonical_request_digest(request),
        "request": request,
        "status": CurationStatus.CURATED,
        "package": _package(),
        "findings": (),
        "abstention_reason": None,
        "parent_target": "protein-RNA discordance",
        "emits_parent": False,
        "support_decision": SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="curated_reference_truth",
            rationale="The declared reference package is complete and locked.",
        ),
        "uncertainty": _uncertainty(),
        "provenance": _provenance(request),
        "evidence": (_evidence("m2201.result.evidence"),),
        "limitations": (
            Limitation(
                code="provisional_no_issuer_authentication",
                statement="Caller-declared material does not authenticate issuer authority.",
            ),
        ),
        "human_review_required": True,
        "result_digest": "sha256:" + "0" * 64,
    }
    provisional = ProteinRnaDiscordanceReferenceTruthResult.model_construct(**payload)
    payload["result_digest"] = result_payload_digest(provisional)
    return ProteinRnaDiscordanceReferenceTruthResult(**payload)


def test_request_binds_m2108_media_and_exact_source_set() -> None:
    request = _request()
    assert request.upstream_result.media_type == M2201_M2108_INPUT_MEDIA_TYPE
    payload = request.model_dump(mode="python")
    payload["upstream_result"]["media_type"] = "application/json"
    with pytest.raises(ValidationError, match="M21-08 result media type"):
        CurateProteinRnaDiscordanceReferenceTruthRequest(**payload)

    payload = request.model_dump(mode="python")
    payload["source_artifacts"] = (payload["source_artifacts"][1],)
    with pytest.raises(ValidationError, match="include the M21-08 result"):
        CurateProteinRnaDiscordanceReferenceTruthRequest(**payload)


def test_request_closes_ids_context_and_challenge_set() -> None:
    request = _request()
    payload = request.model_dump(mode="python")
    payload["context"]["request_id"] = "different-request"
    with pytest.raises(ValidationError, match="context request id"):
        CurateProteinRnaDiscordanceReferenceTruthRequest(**payload)

    payload = request.model_dump(mode="python")
    payload["references"][1]["challenge_set"] = False
    with pytest.raises(ValidationError, match="challenge-set kind"):
        CurateProteinRnaDiscordanceReferenceTruthRequest(**payload)

    payload = request.model_dump(mode="python")
    payload["challenge_set_ids"] = ("unknown",)
    with pytest.raises(ValidationError, match="known reference"):
        CurateProteinRnaDiscordanceReferenceTruthRequest(**payload)

    payload = request.model_dump(mode="python")
    payload["inclusions"] = payload["inclusions"][:-1]
    with pytest.raises(ValidationError, match="classify every item"):
        CurateProteinRnaDiscordanceReferenceTruthRequest(**payload)


def test_package_lock_and_partition_closure_are_immutable() -> None:
    package = _package()
    assert package.lock_digest == reference_truth_package_digest(package)
    changed = package.model_dump(mode="python")
    changed["lock_digest"] = "sha256:" + "f" * 64
    with pytest.raises(ValidationError, match="lock digest"):
        ReferenceTruthPackage(**changed)

    changed = package.model_dump(mode="python")
    changed["references"][0]["kind"] = ReferenceKind.POSITIVE_CONTROL
    with pytest.raises(ValidationError, match="references may only"):
        ReferenceTruthPackage(**changed)

    changed = package.model_dump(mode="python")
    changed["controls"][0]["kind"] = ReferenceKind.CALIBRATOR
    with pytest.raises(ValidationError, match="controls must"):
        ReferenceTruthPackage(**changed)


def test_adjudication_and_result_replay_closure_are_fail_closed() -> None:
    rejected = AdjudicationRecord(
        reference_id="rejected",
        status=AdjudicationStatus.REJECTED,
        reviewer_tokens=("a", "b"),
        agreement_statement="No agreement.",
        disagreement_statement="Reviewers disagree.",
        evidence=(_evidence("rejected.evidence"),),
    )
    assert rejected.status is AdjudicationStatus.REJECTED
    with pytest.raises(ValidationError, match="disagreement statement"):
        AdjudicationRecord(
            reference_id="rejected",
            status=AdjudicationStatus.REJECTED,
            reviewer_tokens=("a", "b"),
            agreement_statement="No agreement.",
            evidence=(_evidence("rejected.invalid"),),
        )
    request = _request()
    result = _result(request)
    assert result.result_id == result_identifier(request)
    assert result.result_digest == result_payload_digest(result)
    assert result.provenance.input_digests[0] == request.upstream_result.digest

    tampered = result.model_dump(mode="python")
    tampered["result_id"] = "m2201.result.tampered"
    with pytest.raises(ValidationError, match="deterministically bound"):
        ProteinRnaDiscordanceReferenceTruthResult(**tampered)

    tampered = result.model_dump(mode="python")
    tampered["provenance"]["module_id"] = "GLIO-PROTEOGEN-M21-08"
    with pytest.raises(ValidationError, match="provenance module id"):
        ProteinRnaDiscordanceReferenceTruthResult(**tampered)

    finding = CurationFinding(
        finding_id="duplicate",
        code=CurationFindingCode.LOCK_INCOMPLETE,
        message="Duplicate finding.",
    ).model_dump(mode="python")
    tampered = result.model_dump(mode="python")
    tampered["findings"] = (finding, finding)
    with pytest.raises(ValidationError, match="finding ids"):
        ProteinRnaDiscordanceReferenceTruthResult(**tampered)
