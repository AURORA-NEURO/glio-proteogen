"""Adversarial contract, replay, and conflict-preservation tests for M19-02."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m19_02 import (
    M1902_M1901_INPUT_MEDIA_TYPE,
    AlignedEvidenceBundle,
    AlignmentConfiguration,
    AlignmentDimension,
    AlignmentFinding,
    AlignmentFindingCode,
    AlignmentObservation,
    AlignmentObservationStatus,
    AlignmentStatus,
    AlignProteotypeSourcesRequest,
    DiscrepancyMapEntry,
    DiscrepancySeverity,
    ProteotypeAlignmentResult,
    canonical_request_digest,
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

_WHEN = datetime(2026, 1, 1, tzinfo=UTC)
_DIMENSIONS = tuple(AlignmentDimension)


def _artifact(label: str, *, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1902": label}),
        media_type=media_type,
    )


def _evidence(label: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(f"evidence.{label}"),
        role="evidence",
        claim="M19-02 caller-declared alignment evidence.",
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="Alignment itself does not estimate a biological probability.",
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=("Sensitivity remains explicit in the aligned evidence bundle.",),
    )


def _context(request_id: str = "request.m1902") -> ExecutionContext:
    accepted = UpstreamDecisionState.ACCEPTED
    return ExecutionContext(
        request_id=request_id,
        actor_id="actor.test",
        occurred_at=_WHEN,
        references=ContextReferences(
            approved_configuration=UpstreamDecisionReference(
                decision_id="decision.configuration",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("control.configuration"),
            ),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("identity"),
                evidence=_artifact("control.identity"),
            ),
            provenance=UpstreamDecisionReference(
                decision_id="decision.provenance",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("control.provenance"),
            ),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("control.consent"),
            ),
            quality=UpstreamDecisionReference(
                decision_id="decision.quality",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("control.quality"),
            ),
            support=UpstreamDecisionReference(
                decision_id="decision.support",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("control.support"),
            ),
            intended_use=UpstreamDecisionReference(
                decision_id="decision.intended",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("control.intended"),
            ),
        ),
    )


def _configuration() -> AlignmentConfiguration:
    return AlignmentConfiguration(
        configuration_id="configuration.m1902",
        version="1.0.0",
        required_dimensions=_DIMENSIONS,
        evidence=(_evidence("configuration"),),
    )


def _observation(
    dimension: AlignmentDimension,
    *,
    status: AlignmentObservationStatus = AlignmentObservationStatus.ALIGNED,
    observed_values: tuple[str, ...] | None = None,
) -> AlignmentObservation:
    reference = f"value.{dimension.value}"
    values = observed_values if observed_values is not None else (reference, reference)
    return AlignmentObservation(
        observation_id=f"observation.{dimension.value}",
        dimension=dimension,
        source_ids=("artifact.upstream", "artifact.proteome"),
        reference_value=reference,
        observed_values=values,
        status=status,
        rationale="Locked fixture comparison across source artifacts.",
        evidence=(_evidence(f"observation.{dimension.value}"),),
    )


def _discrepancy(
    dimension: AlignmentDimension,
    *,
    severity: DiscrepancySeverity = DiscrepancySeverity.MATERIAL,
    review_required: bool = False,
) -> DiscrepancyMapEntry:
    return DiscrepancyMapEntry(
        discrepancy_id=f"discrepancy.{dimension.value}",
        dimension=dimension,
        source_ids=("artifact.upstream", "artifact.proteome"),
        severity=severity,
        description="The source values disagree and are retained for review.",
        review_required=review_required,
        evidence=(_evidence(f"discrepancy.{dimension.value}"),),
    )


def _request(
    *,
    observations: tuple[AlignmentObservation, ...] | None = None,
    discrepancies: tuple[DiscrepancyMapEntry, ...] = (),
    context: ExecutionContext | None = None,
    upstream: ArtifactReference | None = None,
    source_artifacts: tuple[ArtifactReference, ...] | None = None,
) -> AlignProteotypeSourcesRequest:
    upstream_ref = upstream or _artifact("upstream", media_type=M1902_M1901_INPUT_MEDIA_TYPE)
    artifacts = source_artifacts or (upstream_ref, _artifact("proteome"))
    return AlignProteotypeSourcesRequest(
        request_id="request.m1902",
        context=context or _context(),
        upstream_result=upstream_ref,
        source_artifacts=artifacts,
        observations=observations or tuple(_observation(dimension) for dimension in _DIMENSIONS),
        discrepancies=discrepancies,
        configuration=_configuration(),
    )


def _control_records(context: ExecutionContext) -> tuple[ControlDecisionRecord, ...]:
    refs = context.references
    return (
        ControlDecisionRecord(
            role=ControlRole.APPROVED_CONFIGURATION,
            decision_id=refs.approved_configuration.decision_id,
            state=refs.approved_configuration.state.value,
            policy_version=refs.approved_configuration.policy_version,
            evidence_digest=refs.approved_configuration.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.IDENTITY_LINEAGE,
            decision_id=refs.identity_lineage.decision_id,
            state=refs.identity_lineage.state.value,
            policy_version=refs.identity_lineage.policy_version,
            evidence_digest=refs.identity_lineage.evidence.digest,
            subject_digest=refs.identity_lineage.binding_digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.PROVENANCE,
            decision_id=refs.provenance.decision_id,
            state=refs.provenance.state.value,
            policy_version=refs.provenance.policy_version,
            evidence_digest=refs.provenance.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.CONSENT,
            decision_id=refs.consent.decision_id,
            state=refs.consent.state.value,
            policy_version=refs.consent.policy_version,
            evidence_digest=refs.consent.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.QUALITY,
            decision_id=refs.quality.decision_id,
            state=refs.quality.state.value,
            policy_version=refs.quality.policy_version,
            evidence_digest=refs.quality.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.SUPPORT,
            decision_id=refs.support.decision_id,
            state=refs.support.state.value,
            policy_version=refs.support.policy_version,
            evidence_digest=refs.support.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.INTENDED_USE,
            decision_id=refs.intended_use.decision_id,
            state=refs.intended_use.state.value,
            policy_version=refs.intended_use.policy_version,
            evidence_digest=refs.intended_use.evidence.digest,
        ),
    )


def _provenance(request: AlignProteotypeSourcesRequest) -> ProvenanceRecord:
    return ProvenanceRecord(
        activity_id="activity.m1902",
        actor_id=request.context.actor_id,
        module_id="GLIO-PROTEOGEN-M19-02",
        module_version="0.1.0-provisional",
        generated_at=request.context.occurred_at,
        input_digests=tuple(item.digest for item in request.source_artifacts),
        configuration_digest=sha256_digest(request.configuration),
        consent_decision_id=request.context.references.consent.decision_id,
        consent_state=request.context.references.consent.state,
        consent_policy_version=request.context.references.consent.policy_version,
        consent_evidence_digest=request.context.references.consent.evidence.digest,
        control_decisions=_control_records(request.context),
    )


def _bundle(request: AlignProteotypeSourcesRequest) -> AlignedEvidenceBundle:
    return AlignedEvidenceBundle(
        bundle_id="bundle.m1902",
        version="1.0.0",
        source_artifacts=request.source_artifacts,
        observations=request.observations,
        discrepancies=request.discrepancies,
        configuration=request.configuration,
        evidence=(_evidence("bundle"),),
    )


def _result(  # noqa: PLR0913
    *,
    request: AlignProteotypeSourcesRequest | None = None,
    status: AlignmentStatus = AlignmentStatus.ALIGNED,
    bundle: AlignedEvidenceBundle | None = None,
    support_status: SupportStatus = SupportStatus.SUPPORTED,
    findings: tuple[AlignmentFinding, ...] = (),
    abstention_reason: str | None = None,
    human_review_required: bool = False,
) -> ProteotypeAlignmentResult:
    actual_request = request or _request()
    actual_bundle = (
        bundle
        if bundle is not None
        else (_bundle(actual_request) if status is AlignmentStatus.ALIGNED else None)
    )
    provisional = ProteotypeAlignmentResult.model_construct(
        result_id=f"result.{canonical_request_digest(actual_request).removeprefix('sha256:')}",
        request_digest=canonical_request_digest(actual_request),
        result_digest="sha256:" + "a" * 64,
        request=actual_request,
        status=status,
        aligned_bundle=actual_bundle,
        findings=findings,
        abstention_reason=abstention_reason,
        support_decision=SupportDecision(
            status=support_status,
            reason_code="supported_alignment"
            if status is AlignmentStatus.ALIGNED
            else "alignment_abstained",
            rationale="Locked contract fixture support decision.",
        ),
        uncertainty=_uncertainty(),
        provenance=_provenance(actual_request),
        evidence=(_evidence("result"),),
        limitations=(
            Limitation(
                code="provisional_abi",
                statement="M19-02 remains provisional pending owner confirmation.",
            ),
        ),
        human_review_required=human_review_required,
    )
    return ProteotypeAlignmentResult.model_validate(
        provisional.model_copy(
            update={"result_digest": result_payload_digest(provisional)}
        ).model_dump(mode="python")
    )


def test_every_alignment_dimension_is_required_and_conflicts_are_closed() -> None:
    request = _request()
    assert tuple(item.dimension for item in request.observations) == _DIMENSIONS
    with pytest.raises(ValidationError, match="exactly one observation"):
        _request(observations=request.observations[:-1])
    conflict = _observation(
        AlignmentDimension.TIME,
        status=AlignmentObservationStatus.CONFLICTED,
        observed_values=("value.time", "other.time"),
    )
    with pytest.raises(ValidationError, match="differing observed value"):
        _observation(
            AlignmentDimension.TIME,
            status=AlignmentObservationStatus.CONFLICTED,
            observed_values=("value.time", "value.time"),
        )
    with pytest.raises(ValidationError, match="matching discrepancy"):
        _request(
            observations=tuple(
                conflict if item.dimension is AlignmentDimension.TIME else item
                for item in request.observations
            )
        )
    request_with_conflict = _request(
        observations=tuple(
            conflict if item.dimension is AlignmentDimension.TIME else item
            for item in request.observations
        ),
        discrepancies=(_discrepancy(AlignmentDimension.TIME),),
    )
    assert request_with_conflict.discrepancies[0].dimension is AlignmentDimension.TIME
    assert _bundle(request_with_conflict).discrepancies
    with pytest.raises(ValidationError, match="conflicting observed value"):
        _observation(
            AlignmentDimension.TIME,
            observed_values=("value.time", "other.time"),
        )
    with pytest.raises(ValidationError, match="all seven dimensions"):
        AlignmentConfiguration.model_validate(
            _configuration().model_dump(mode="python")
            | {"required_dimensions": (*_DIMENSIONS[:-1], AlignmentDimension.SAMPLE)}
        )


def test_sources_and_evidence_are_content_addressed_and_unique() -> None:
    request = _request()
    duplicate = _artifact("upstream", media_type=M1902_M1901_INPUT_MEDIA_TYPE)
    with pytest.raises(ValidationError, match="source artifact ids"):
        _request(source_artifacts=(duplicate, duplicate))
    same_digest_different_id = duplicate.model_copy(update={"artifact_id": "artifact.other"})
    with pytest.raises(ValidationError, match="source artifact digests"):
        _request(source_artifacts=(duplicate, same_digest_different_id))
    with pytest.raises(ValidationError, match="include the bound"):
        _request(source_artifacts=(_artifact("other"), _artifact("proteome")))
    assert canonical_request_digest(request) == canonical_request_digest(
        request.model_dump(mode="json")
    )


def test_configuration_and_discrepancy_require_explicit_review_closure() -> None:
    with pytest.raises(ValidationError, match="critical discrepancy"):
        _discrepancy(AlignmentDimension.TIME, severity=DiscrepancySeverity.CRITICAL)
    critical = _discrepancy(
        AlignmentDimension.TIME,
        severity=DiscrepancySeverity.CRITICAL,
        review_required=True,
    )
    request = _request(
        observations=tuple(
            _observation(
                item.dimension,
                status=AlignmentObservationStatus.CONFLICTED,
                observed_values=(f"value.{item.dimension.value}", "other.value"),
            )
            if item.dimension is AlignmentDimension.TIME
            else item
            for item in _request().observations
        ),
        discrepancies=(critical,),
    )
    with pytest.raises(ValidationError, match="review-required discrepancy"):
        _result(request=request, bundle=_bundle(request))


def test_request_and_bundle_preserve_source_reference_closure() -> None:
    request = _request()
    unknown_observation = request.observations[0].model_copy(
        update={"source_ids": ("artifact.unknown", "artifact.proteome")}
    )
    with pytest.raises(ValidationError, match="observation references"):
        AlignProteotypeSourcesRequest.model_validate(
            request.model_dump(mode="python")
            | {
                "observations": (unknown_observation, *request.observations[1:]),
            }
        )
    conflict = _observation(
        AlignmentDimension.TIME,
        status=AlignmentObservationStatus.CONFLICTED,
        observed_values=("value.time", "other.time"),
    )
    unknown_discrepancy = _discrepancy(AlignmentDimension.TIME).model_copy(
        update={"source_ids": ("artifact.upstream", "artifact.unknown")}
    )
    with pytest.raises(ValidationError, match="discrepancy references"):
        AlignProteotypeSourcesRequest.model_validate(
            request.model_dump(mode="python")
            | {
                "observations": tuple(
                    conflict if item.dimension is AlignmentDimension.TIME else item
                    for item in request.observations
                ),
                "discrepancies": (unknown_discrepancy,),
            }
        )


def test_result_identity_replay_and_tamper_are_fail_closed() -> None:
    result = _result()
    assert result.result_id.removeprefix("result.") == result.request_digest.removeprefix("sha256:")
    assert result_payload_digest(result) == result.result_digest
    with pytest.raises(ValidationError, match="request digest"):
        ProteotypeAlignmentResult.model_validate(
            result.model_copy(update={"request_digest": "sha256:" + "0" * 64})
        )
    with pytest.raises(ValidationError, match="identifier"):
        ProteotypeAlignmentResult.model_validate(
            result.model_copy(update={"result_id": "result.tampered"})
        )
    with pytest.raises(ValidationError, match="result digest"):
        ProteotypeAlignmentResult.model_validate(
            result.model_copy(update={"result_digest": "sha256:" + "0" * 64})
        )
    with pytest.raises(ValidationError, match="provenance"):
        ProteotypeAlignmentResult.model_validate(
            result.model_copy(
                update={
                    "provenance": result.provenance.model_copy(
                        update={"module_id": "GLIO-PROTEOGEN-M19-01"}
                    )
                }
            )
        )
    assert result.aligned_bundle is not None
    with pytest.raises(ValidationError, match="exact request alignment material"):
        ProteotypeAlignmentResult.model_validate(
            result.model_copy(
                update={
                    "aligned_bundle": result.aligned_bundle.model_copy(
                        update={
                            "source_artifacts": (
                                result.request.source_artifacts[0],
                                result.request.source_artifacts[1].model_copy(
                                    update={"digest": sha256_digest("tampered.source")}
                                ),
                            )
                        }
                    )
                }
            )
        )


def test_abstention_requires_typed_findings_and_review_for_biological_conflict() -> None:
    finding = AlignmentFinding(
        finding_id="finding.conflict",
        code=AlignmentFindingCode.BIOLOGICAL_CONFLICT_REVIEW,
        message="The biological context remains irreconcilable.",
        evidence=(_evidence("finding.conflict"),),
    )
    result = _result(
        status=AlignmentStatus.ABSTAINED,
        support_status=SupportStatus.REVIEW_REQUIRED,
        findings=(finding,),
        abstention_reason="Irreconcilable biological conflict requires review.",
        human_review_required=True,
    )
    assert result.aligned_bundle is None
    assert result.status is AlignmentStatus.ABSTAINED
    with pytest.raises(ValidationError, match="typed findings"):
        _result(
            status=AlignmentStatus.ABSTAINED,
            support_status=SupportStatus.UNSUPPORTED,
            abstention_reason="Unsupported source.",
        )
    with pytest.raises(ValidationError, match="human review"):
        _result(
            status=AlignmentStatus.ABSTAINED,
            support_status=SupportStatus.REVIEW_REQUIRED,
            findings=(finding,),
            abstention_reason="Review is required.",
        )


def test_result_status_closure_rejects_unsafe_combinations() -> None:
    result = _result()
    with pytest.raises(ValidationError, match="supported evidence bundle"):
        ProteotypeAlignmentResult.model_validate(result.model_copy(update={"aligned_bundle": None}))
    abstained = _result(
        status=AlignmentStatus.ABSTAINED,
        support_status=SupportStatus.REVIEW_REQUIRED,
        findings=(
            AlignmentFinding(
                finding_id="finding.review",
                code=AlignmentFindingCode.INPUT_INCOMPLETE,
                message="Input is incomplete and requires review.",
            ),
        ),
        abstention_reason="Input is incomplete.",
        human_review_required=True,
    )
    with pytest.raises(ValidationError, match="no bundle"):
        ProteotypeAlignmentResult.model_validate(
            abstained.model_copy(update={"aligned_bundle": _bundle(_request())})
        )
    with pytest.raises(ValidationError, match="safe non-supported"):
        _result(
            status=AlignmentStatus.ABSTAINED,
            support_status=SupportStatus.SUPPORTED,
            findings=abstained.findings,
            abstention_reason="Input is incomplete.",
            human_review_required=True,
        )


def test_upstream_media_type_and_context_binding_are_not_inferred() -> None:
    with pytest.raises(ValidationError, match="M19-01"):
        _request(upstream=_artifact("upstream.bad"))
    with pytest.raises(ValidationError, match="context request id"):
        _request(context=_context("request.other"))
