"""Negative-path and replay hardening tests for M05-07."""

from datetime import UTC, datetime
from typing import Any, cast

import pytest
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m05_07 import (
    M0507_M0506_RESULT_MEDIA_TYPE,
    PtmLocalizationAbstentionCode,
    PtmLocalizationDeclaredSupportState,
    PtmLocalizationDimensionSupportDecision,
    PtmLocalizationRemediationPath,
    PtmLocalizationSupportDimension,
    PtmLocalizationSupportDisposition,
    PtmLocalizationSupportFact,
    PtmLocalizationSupportPolicy,
    PtmLocalizationSupportPrerequisites,
    PtmLocalizationSupportReceipt,
    PtmLocalizationSupportRouteResult,
    RoutePtmLocalizationSupportRequest,
    canonical_request_digest,
    receipt_digest,
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

_DIGEST = "sha256:" + "a" * 64
_DIMENSIONS = tuple(PtmLocalizationSupportDimension)


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest=_DIGEST,
        media_type=media_type,
    )


def _context(request_id: str = "request.1") -> ExecutionContext:
    evidence = _artifact("control.evidence")
    return ExecutionContext(
        request_id=request_id,
        actor_id="actor.1",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=UpstreamDecisionReference(
                decision_id="config.1",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=evidence,
            ),
            identity_lineage=IdentityLineageReference(
                decision_id="identity.1",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=_DIGEST,
                evidence=evidence,
            ),
            provenance=UpstreamDecisionReference(
                decision_id="provenance.1",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=evidence,
            ),
            consent=ConsentReference(
                decision_id="consent.1",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=evidence,
            ),
            quality=UpstreamDecisionReference(
                decision_id="quality.1",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=evidence,
            ),
            support=UpstreamDecisionReference(
                decision_id="support.1",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=evidence,
            ),
            intended_use=UpstreamDecisionReference(
                decision_id="use.1",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=evidence,
            ),
        ),
    )


def _policy(
    dimensions: tuple[PtmLocalizationSupportDimension, ...] = _DIMENSIONS,
) -> PtmLocalizationSupportPolicy:
    return PtmLocalizationSupportPolicy(
        policy_id="policy.1",
        version="1.0.0",
        dimensions=dimensions,
        reviewed_by="reviewer.1",
        reviewed_at=datetime(2026, 1, 1, tzinfo=UTC),
        evidence=_artifact("policy.evidence"),
    )


def _facts() -> tuple[PtmLocalizationSupportFact, ...]:
    return tuple(
        PtmLocalizationSupportFact(
            dimension=dimension,
            state=PtmLocalizationDeclaredSupportState.OBSERVED,
            decision=PtmLocalizationDimensionSupportDecision.SUPPORTED,
            rationale="Reviewed support evidence is present.",
        )
        for dimension in _DIMENSIONS
    )


def _request(**updates: object) -> RoutePtmLocalizationSupportRequest:
    values: dict[str, object] = {
        "request_id": "request.1",
        "context": _context(),
        "prerequisites": PtmLocalizationSupportPrerequisites(
            harmonization_result=_artifact("harmonized", M0507_M0506_RESULT_MEDIA_TYPE)
        ),
        "policy": _policy(),
        "declared_facts": _facts(),
    }
    values.update(updates)
    return RoutePtmLocalizationSupportRequest(**cast("Any", values))


def _receipt(
    request: RoutePtmLocalizationSupportRequest,
    disposition: PtmLocalizationSupportDisposition = PtmLocalizationSupportDisposition.SUPPORTED,
    **updates: object,
) -> PtmLocalizationSupportReceipt:
    values: dict[str, object] = {
        "request_digest": canonical_request_digest(request),
        "disposition": disposition,
        "evidence": (),
        "receipt_digest": _DIGEST,
    }
    if disposition is PtmLocalizationSupportDisposition.ABSTAINED:
        values.update(
            {
                "abstention_code": PtmLocalizationAbstentionCode.DIMENSION_OUTSIDE_DOMAIN,
                "remediation": (PtmLocalizationRemediationPath.CORRECT_SUPPORT_DECLARATION,),
                "unsupported_dimensions": (PtmLocalizationSupportDimension.ASSAY,),
            }
        )
    values.update(updates)
    values["receipt_digest"] = receipt_digest(
        PtmLocalizationSupportReceipt.model_construct(**cast("Any", values))
    )
    return PtmLocalizationSupportReceipt(**cast("Any", values))


def _provenance(request: RoutePtmLocalizationSupportRequest) -> ProvenanceRecord:
    references = request.context.references
    controls = (
        ControlDecisionRecord(
            role=ControlRole.APPROVED_CONFIGURATION,
            decision_id=references.approved_configuration.decision_id,
            state=references.approved_configuration.state.value,
            policy_version=references.approved_configuration.policy_version,
            evidence_digest=references.approved_configuration.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.IDENTITY_LINEAGE,
            decision_id=references.identity_lineage.decision_id,
            state=references.identity_lineage.state.value,
            policy_version=references.identity_lineage.policy_version,
            evidence_digest=references.identity_lineage.evidence.digest,
            subject_digest=references.identity_lineage.binding_digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.PROVENANCE,
            decision_id=references.provenance.decision_id,
            state=references.provenance.state.value,
            policy_version=references.provenance.policy_version,
            evidence_digest=references.provenance.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.CONSENT,
            decision_id=references.consent.decision_id,
            state=references.consent.state.value,
            policy_version=references.consent.policy_version,
            evidence_digest=references.consent.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.QUALITY,
            decision_id=references.quality.decision_id,
            state=references.quality.state.value,
            policy_version=references.quality.policy_version,
            evidence_digest=references.quality.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.SUPPORT,
            decision_id=references.support.decision_id,
            state=references.support.state.value,
            policy_version=references.support.policy_version,
            evidence_digest=references.support.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.INTENDED_USE,
            decision_id=references.intended_use.decision_id,
            state=references.intended_use.state.value,
            policy_version=references.intended_use.policy_version,
            evidence_digest=references.intended_use.evidence.digest,
        ),
    )
    return ProvenanceRecord(
        activity_id="activity.1",
        actor_id=request.context.actor_id,
        module_id="GLIO-PROTEOGEN-M05-07",
        module_version="0.1.0-provisional",
        generated_at=request.context.occurred_at,
        input_digests=(_DIGEST,),
        configuration_digest=_DIGEST,
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=controls,
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="Support routing does not estimate this uncertainty dimension.",
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


def _result(
    request: RoutePtmLocalizationSupportRequest,
    disposition: PtmLocalizationSupportDisposition = PtmLocalizationSupportDisposition.SUPPORTED,
    **updates: object,
) -> PtmLocalizationSupportRouteResult:
    request_hash = canonical_request_digest(request)
    receipt = _receipt(request, disposition)
    values: dict[str, object] = {
        "result_id": "result.1",
        "request_digest": request_hash,
        "result_digest": _DIGEST,
        "request": request,
        "receipt": receipt,
        "support_decision": SupportDecision(
            status=(
                SupportStatus.SUPPORTED
                if disposition is PtmLocalizationSupportDisposition.SUPPORTED
                else SupportStatus.REVIEW_REQUIRED
            ),
            reason_code="support_route",
            rationale="All declared support dimensions were evaluated.",
        ),
        "disposition": disposition,
        "parent_target": "variant_peptide",
        "uncertainty": _uncertainty(),
        "provenance": _provenance(request),
        "limitations": (
            Limitation(
                code="routing_only",
                statement="This route is not a scientific finding or negative result.",
            ),
        ),
    }
    if disposition is PtmLocalizationSupportDisposition.ABSTAINED:
        values.update(
            {
                "abstention_code": PtmLocalizationAbstentionCode.DIMENSION_OUTSIDE_DOMAIN,
                "remediation": (PtmLocalizationRemediationPath.CORRECT_SUPPORT_DECLARATION,),
            }
        )
    values.update(updates)
    values["result_digest"] = result_payload_digest(
        PtmLocalizationSupportRouteResult.model_construct(**cast("Any", values))
    )
    return PtmLocalizationSupportRouteResult(**cast("Any", values))


def test_policy_rejects_missing_dimension() -> None:
    with pytest.raises(ValidationError, match=r"at least 8|all eight"):
        _policy(_DIMENSIONS[:-1])


def test_policy_rejects_duplicate_dimension() -> None:
    with pytest.raises(ValidationError, match="all eight"):
        _policy((*_DIMENSIONS[:-1], _DIMENSIONS[0]))


def test_observed_support_cannot_be_indeterminate() -> None:
    with pytest.raises(ValidationError, match="observed support"):
        PtmLocalizationSupportFact(
            dimension=PtmLocalizationSupportDimension.ASSAY,
            state=PtmLocalizationDeclaredSupportState.OBSERVED,
            decision=PtmLocalizationDimensionSupportDecision.INDETERMINATE,
            rationale="The evidence is present.",
        )


def test_missing_support_cannot_be_supported() -> None:
    with pytest.raises(ValidationError, match="cannot be supported"):
        PtmLocalizationSupportFact(
            dimension=PtmLocalizationSupportDimension.ASSAY,
            state=PtmLocalizationDeclaredSupportState.MISSING,
            decision=PtmLocalizationDimensionSupportDecision.SUPPORTED,
            rationale="No evidence was supplied.",
        )


def test_request_rejects_duplicate_facts() -> None:
    facts = _facts()
    with pytest.raises(ValidationError, match="exactly one fact"):
        _request(declared_facts=(*facts[:-1], facts[0]))


def test_request_binds_execution_context_identity() -> None:
    with pytest.raises(ValidationError, match="request id"):
        _request(context=_context("request.other"))


def test_prerequisite_rejects_wrong_upstream_media_type() -> None:
    with pytest.raises(ValidationError, match="M05-06 result media type"):
        PtmLocalizationSupportPrerequisites(harmonization_result=_artifact("harmonized"))


def test_request_rejects_unknown_fields_strictly() -> None:
    raw = _request().model_dump(mode="python")
    raw["unexpected"] = True
    with pytest.raises(ValidationError, match="extra"):
        TypeAdapter(RoutePtmLocalizationSupportRequest).validate_python(raw, strict=True)


def test_supported_receipt_cannot_carry_abstention_material() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="supported receipt"):
        _receipt(
            request,
            remediation=(PtmLocalizationRemediationPath.CORRECT_SUPPORT_DECLARATION,),
        )


def test_abstained_receipt_requires_remediation_and_dimensions() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="abstained receipt"):
        _receipt(
            request,
            PtmLocalizationSupportDisposition.ABSTAINED,
            remediation=(),
            unsupported_dimensions=(),
        )


def test_receipt_digest_tampering_is_rejected() -> None:
    request = _request()
    receipt = _receipt(request)
    with pytest.raises(ValidationError, match="receipt digest"):
        PtmLocalizationSupportReceipt.model_validate(
            {**receipt.model_dump(mode="python"), "receipt_digest": "sha256:" + "b" * 64}
        )


def test_result_rejects_mismatched_receipt_disposition() -> None:
    request = _request()
    receipt = _receipt(request, PtmLocalizationSupportDisposition.ABSTAINED)
    with pytest.raises(ValidationError, match="does not match"):
        _result(request, receipt=receipt)


def test_result_rejects_request_digest_tampering() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="exact request"):
        _result(request, request_digest="sha256:" + "c" * 64)


def test_result_rejects_result_digest_tampering() -> None:
    request = _request()
    result = _result(request)
    with pytest.raises(ValidationError, match="result digest"):
        PtmLocalizationSupportRouteResult.model_validate(
            {**result.model_dump(mode="python"), "result_digest": "sha256:" + "d" * 64}
        )


def test_abstained_result_requires_safe_support_status() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="safe status"):
        _result(
            request,
            PtmLocalizationSupportDisposition.ABSTAINED,
            support_decision=SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="support_route",
                rationale="Incorrectly marked supported.",
            ),
        )
