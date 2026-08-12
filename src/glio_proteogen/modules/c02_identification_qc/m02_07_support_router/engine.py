"""Deterministic C02 joint support-envelope routing and compact receipt reduction."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m02_04 import (
    IdentificationAssayProfile,
    IdentificationQualityMetricCode,
    IdentificationQualityProfile,
)
from glio_proteogen.contracts.m02_06 import (
    HarmonizationValueState,
    IdentificationHarmonizationResult,
    IdentificationTechnicalFactor,
)
from glio_proteogen.contracts.m02_07 import (
    M0207_AUTHORITY_LIMITATION_CODE,
    M0207_AUTHORITY_LIMITATION_STATEMENT,
    M0207_CONTRACT_VERSION,
    M0207_MODULE_ID,
    M0207_SENSITIVITY_NOTES,
    M0207_SUPPORT_LIMITATION_CODE,
    M0207_SUPPORT_LIMITATION_STATEMENT,
    M0207_UNCERTAINTY_RATIONALES,
    DeclaredSupportFact,
    IdentificationContextReceipt,
    IdentificationHarmonizationSupportReceipt,
    IdentificationQualitySupportReceipt,
    IdentificationSupportDisposition,
    IdentificationSupportPolicy,
    IdentificationSupportPrerequisites,
    IdentificationSupportProfile,
    IdentificationSupportRouteResult,
    RouteIdentificationSupportRequest,
    configuration_digest,
    context_digest,
    context_receipt_digest,
    derive_support_route,
    fact_digest,
    policy_digest,
    prerequisites_digest,
    profile_digest,
    request_manifest_digest,
    support_route_evidence_index,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    ExecutionContext,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
)

_REQUEST_ADAPTER: Final = TypeAdapter(RouteIdentificationSupportRequest)
_ASSAY_ADAPTER: Final = TypeAdapter(IdentificationAssayProfile)
_QUALITY_ADAPTER: Final = TypeAdapter(IdentificationQualityProfile)
_HARMONIZATION_ADAPTER: Final = TypeAdapter(IdentificationHarmonizationResult)
_RESULT_MEDIA_TYPE: Final = "application/json"
_LIMITATIONS: Final = (
    Limitation(
        code=M0207_SUPPORT_LIMITATION_CODE,
        statement=M0207_SUPPORT_LIMITATION_STATEMENT,
    ),
    Limitation(
        code=M0207_AUTHORITY_LIMITATION_CODE,
        statement=M0207_AUTHORITY_LIMITATION_STATEMENT,
    ),
)


class IdentificationSupportAuthorizationError(ValueError):
    """Denied controls detected without traversing support-domain payloads."""

    def __init__(self) -> None:
        super().__init__("upstream controls do not authorize identification support routing")


class IdentificationSupportReceiptError(ValueError):
    """Strict upstream results do not form one compact M02-07 prerequisite chain."""

    @classmethod
    def missing_identity(cls) -> IdentificationSupportReceiptError:
        return cls("upstream result lacks an identity subject binding")

    @classmethod
    def assay_mismatch(cls) -> IdentificationSupportReceiptError:
        return cls("assay profile evidence does not bind M02-04")


class M0207SupportRouterEngine:
    """Evaluate complete reviewed envelopes without persistence or learned inference."""

    __slots__ = ()

    def route(self, request: object) -> IdentificationSupportRouteResult:
        preflight_identification_support_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        return _present(validated)


def route_identification_support(request: object) -> IdentificationSupportRouteResult:
    """Public stateless routing entry point."""

    return M0207SupportRouterEngine().route(request)


def preflight_identification_support_authorization(candidate: object) -> None:
    """Reject denied raw requests before declarations, receipts, or hashes are touched."""

    if isinstance(candidate, RouteIdentificationSupportRequest):
        context: object = candidate.context
    elif isinstance(candidate, Mapping):
        context = candidate.get("context")
    else:
        raise IdentificationSupportAuthorizationError
    references = _member(context, "references")
    expected = {
        "approved_configuration": "accepted",
        "identity_lineage": "resolved",
        "provenance": "accepted",
        "consent": "granted",
        "quality": "accepted",
        "support": "accepted",
        "intended_use": "accepted",
    }
    if any(
        _member(_member(references, role), "state") != state for role, state in expected.items()
    ):
        raise IdentificationSupportAuthorizationError


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _identity_subject_digest(
    result: IdentificationQualityProfile | IdentificationHarmonizationResult,
) -> str:
    record = next(
        (
            item
            for item in result.provenance.control_decisions
            if item.role is ControlRole.IDENTITY_LINEAGE
        ),
        None,
    )
    if record is None or record.subject_digest is None:
        raise IdentificationSupportReceiptError.missing_identity()
    return record.subject_digest


def _result_artifact(module: str, version: str, digest: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"result.{module}.{digest.removeprefix('sha256:')}",
        version=version,
        digest=digest,
        media_type=_RESULT_MEDIA_TYPE,
    )


def build_identification_quality_support_receipt(
    assay_profile: object,
    quality_result: object,
) -> IdentificationQualitySupportReceipt:
    """Reduce a strict M02-04 result to its privacy-safe M02-07 receipt."""

    assay = _ASSAY_ADAPTER.validate_python(assay_profile, strict=True)
    quality = _QUALITY_ADAPTER.validate_python(quality_result, strict=True)
    if assay.evidence.digest != quality.assay_profile_evidence_digest:
        raise IdentificationSupportReceiptError.assay_mismatch()
    completeness = next(
        item
        for item in quality.metrics
        if item.metric_code is IdentificationQualityMetricCode.IDENTIFICATION_COMPLETENESS
    )
    return IdentificationQualitySupportReceipt(
        result_digest=quality.result_digest,
        disposition=quality.disposition,
        assay_profile_digest=quality.assay_profile_digest,
        assay_profile_evidence_digest=quality.assay_profile_evidence_digest,
        identity_subject_digest=_identity_subject_digest(quality),
        metric_statuses=tuple(
            item.status for item in sorted(quality.metrics, key=lambda item: item.metric_code.value)
        ),
        completeness_state=completeness.state,
        completeness_status=completeness.status,
        completeness_value=completeness.value,
        artifact=_result_artifact("m0204", quality.result_version, quality.result_digest),
    )


def build_identification_harmonization_support_receipt(
    harmonization_result: object,
) -> IdentificationHarmonizationSupportReceipt:
    """Reduce a strict M02-06 result without copying harmonized scientific values."""

    harmonization = _HARMONIZATION_ADAPTER.validate_python(
        harmonization_result,
        strict=True,
    )
    quality_receipt = next(
        item
        for item in harmonization.upstream_receipts
        if item.module_id == "GLIO-PROTEOGEN-M02-04"
    )
    platform_ids = {
        level.level_id
        for value in harmonization.values
        for level in value.source_observation.factor_levels
        if level.factor is IdentificationTechnicalFactor.PLATFORM
    }
    nonexcluded = tuple(
        value
        for value in harmonization.values
        if value.output_state is not HarmonizationValueState.EXCLUDED
    )
    evaluable = tuple(
        value
        for value in nonexcluded
        if value.output_state is HarmonizationValueState.OBSERVED
        and value.harmonized_value is not None
    )
    return IdentificationHarmonizationSupportReceipt(
        result_digest=harmonization.result_digest,
        disposition=harmonization.disposition,
        m0204_result_digest=quality_receipt.result_digest,
        identity_subject_digest=_identity_subject_digest(harmonization),
        platform_ids=tuple(sorted(platform_ids)),
        total_value_count=len(harmonization.values),
        nonexcluded_value_count=len(nonexcluded),
        evaluable_value_count=len(evaluable),
        artifact=_result_artifact(
            "m0206",
            harmonization.result_version,
            harmonization.result_digest,
        ),
    )


def build_identification_support_prerequisites(
    assay_profile: object,
    quality_result: object,
    harmonization_result: object,
) -> IdentificationSupportPrerequisites:
    """Build one digest- and lineage-closed compact prerequisite bundle."""

    assay = _ASSAY_ADAPTER.validate_python(assay_profile, strict=True)
    return IdentificationSupportPrerequisites(
        assay_profile=assay,
        quality=build_identification_quality_support_receipt(assay, quality_result),
        harmonization=build_identification_harmonization_support_receipt(harmonization_result),
    )


def _canonical_fact(fact: DeclaredSupportFact) -> DeclaredSupportFact:
    return fact.model_copy(
        update={
            "values": tuple(sorted(fact.values)),
            "evidence": tuple(sorted(fact.evidence, key=canonical_json_bytes)),
        }
    )


def _canonical_profile(profile: IdentificationSupportProfile) -> IdentificationSupportProfile:
    return profile.model_copy(
        update={
            "envelopes": tuple(
                sorted(
                    (
                        envelope.model_copy(
                            update={
                                "assay_types": tuple(sorted(envelope.assay_types)),
                                "specimen_terms": tuple(sorted(envelope.specimen_terms)),
                                "disease_class_terms": tuple(sorted(envelope.disease_class_terms)),
                                "quality_statuses": tuple(
                                    sorted(envelope.quality_statuses, key=lambda item: item.value)
                                ),
                                "platform_ids": tuple(sorted(envelope.platform_ids)),
                                "reference_ids": tuple(sorted(envelope.reference_ids)),
                                "intended_use_terms": tuple(sorted(envelope.intended_use_terms)),
                                "required_context_roles": tuple(
                                    sorted(
                                        envelope.required_context_roles,
                                        key=lambda item: item.value,
                                    )
                                ),
                                "remediations": tuple(
                                    sorted(
                                        envelope.remediations,
                                        key=lambda item: item.dimension.value,
                                    )
                                ),
                            }
                        )
                        for envelope in profile.envelopes
                    ),
                    key=lambda item: item.envelope_id,
                )
            )
        }
    )


def _canonical_prerequisites(
    prerequisites: IdentificationSupportPrerequisites,
) -> IdentificationSupportPrerequisites:
    return prerequisites.model_copy(
        update={
            "quality": prerequisites.quality.model_copy(
                update={
                    "metric_statuses": tuple(
                        sorted(prerequisites.quality.metric_statuses, key=lambda item: item.value)
                    )
                }
            ),
            "harmonization": prerequisites.harmonization.model_copy(
                update={"platform_ids": tuple(sorted(prerequisites.harmonization.platform_ids))}
            ),
        }
    )


def _present(request: RouteIdentificationSupportRequest) -> IdentificationSupportRouteResult:
    prerequisites = _canonical_prerequisites(request.prerequisites)
    profile = _canonical_profile(request.profile)
    policy: IdentificationSupportPolicy = request.policy
    facts = tuple(
        sorted(
            (_canonical_fact(item) for item in request.declared_facts),
            key=lambda item: item.dimension.value,
        )
    )
    contexts = tuple(sorted(request.context_receipts, key=lambda item: item.role.value))
    context_hash = context_digest(request.context)
    prerequisite_hash = prerequisites_digest(prerequisites)
    profile_hash = profile_digest(profile)
    active_policy_hash = policy_digest(policy)
    configuration_hash = configuration_digest(profile, policy)
    request_hash = request_manifest_digest(
        active_context_digest=context_hash,
        active_prerequisites_digest=prerequisite_hash,
        active_profile_digest=profile_hash,
        active_policy_digest=active_policy_hash,
        fact_digests=tuple(fact_digest(item) for item in facts),
        context_receipt_digests=tuple(context_receipt_digest(item) for item in contexts),
        supersedes_result_digest=request.supersedes_result_digest,
    )
    assessments, matches, abstentions = derive_support_route(
        prerequisites,
        profile,
        facts,
        contexts,
    )
    disposition = (
        IdentificationSupportDisposition.SUPPORTED
        if matches
        else IdentificationSupportDisposition.ABSTAINED
    )
    controls = _control_records(request.context)
    suffix = request_hash.removeprefix("sha256:")
    return IdentificationSupportRouteResult(
        route_id=f"route.m0207.{suffix}",
        request_digest=request_hash,
        context_digest=context_hash,
        context=request.context,
        prerequisites_digest=prerequisite_hash,
        prerequisites=prerequisites,
        profile_digest=profile_hash,
        profile=profile,
        policy_digest=active_policy_hash,
        policy=policy,
        configuration_digest=configuration_hash,
        declared_facts=facts,
        context_receipts=contexts,
        disposition=disposition,
        matched_envelope_ids=matches,
        envelope_assessments=assessments,
        abstention_reasons=abstentions,
        support=_support(disposition),
        uncertainty=_uncertainty(),
        provenance=_provenance(
            request.context,
            request_hash,
            context_hash,
            prerequisite_hash,
            profile_hash,
            active_policy_hash,
            configuration_hash,
            prerequisites,
            controls,
        ),
        evidence=_evidence(request.context, profile, policy, prerequisites, facts, contexts),
        limitations=_LIMITATIONS,
        human_review_required=disposition is IdentificationSupportDisposition.ABSTAINED,
        completed_at=request.context.occurred_at,
        supersedes_result_digest=request.supersedes_result_digest,
    )


def _support(disposition: IdentificationSupportDisposition) -> SupportDecision:
    if disposition is IdentificationSupportDisposition.SUPPORTED:
        return SupportDecision(
            status=SupportStatus.LIMITED,
            reason_code="identification_support_confirmed",
            rationale="One reviewed joint identification support envelope was confirmed.",
        )
    return SupportDecision(
        status=SupportStatus.UNSUPPORTED,
        reason_code="identification_support_abstained",
        rationale="No reviewed joint identification support envelope was confirmed.",
    )


def _not_estimable(rationale: str) -> UncertaintyEstimate:
    return UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=rationale)


def _uncertainty() -> UncertaintyProfile:
    return UncertaintyProfile(
        measurement=_not_estimable(M0207_UNCERTAINTY_RATIONALES["measurement"]),
        sampling=_not_estimable(M0207_UNCERTAINTY_RATIONALES["sampling"]),
        parameter=_not_estimable(M0207_UNCERTAINTY_RATIONALES["parameter"]),
        model_form=_not_estimable(M0207_UNCERTAINTY_RATIONALES["model_form"]),
        identification=_not_estimable(M0207_UNCERTAINTY_RATIONALES["identification"]),
        support=_not_estimable(M0207_UNCERTAINTY_RATIONALES["support"]),
        transport=_not_estimable(M0207_UNCERTAINTY_RATIONALES["transport"]),
        sensitivity_notes=M0207_SENSITIVITY_NOTES,
    )


def _control_records(context: ExecutionContext) -> tuple[ControlDecisionRecord, ...]:
    references = context.references
    values = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration, None),
        (
            ControlRole.IDENTITY_LINEAGE,
            references.identity_lineage,
            references.identity_lineage.binding_digest,
        ),
        (ControlRole.PROVENANCE, references.provenance, None),
        (ControlRole.CONSENT, references.consent, None),
        (ControlRole.QUALITY, references.quality, None),
        (ControlRole.SUPPORT, references.support, None),
        (ControlRole.INTENDED_USE, references.intended_use, None),
    )
    return tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=reference.decision_id,
            state=reference.state.value,
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=subject,
        )
        for role, reference, subject in values
    )


def _provenance(  # noqa: PLR0913, PLR0917 - exact closed input digest manifest.
    context: ExecutionContext,
    request_hash: str,
    context_hash: str,
    prerequisite_hash: str,
    profile_hash: str,
    active_policy_hash: str,
    configuration_hash: str,
    prerequisites: IdentificationSupportPrerequisites,
    controls: tuple[ControlDecisionRecord, ...],
) -> ProvenanceRecord:
    references = context.references
    return ProvenanceRecord(
        activity_id=f"activity.m0207.{request_hash.removeprefix('sha256:')}",
        actor_id=context.actor_id,
        module_id=M0207_MODULE_ID,
        module_version=M0207_CONTRACT_VERSION,
        generated_at=context.occurred_at,
        input_digests=tuple(
            sorted(
                {
                    request_hash,
                    context_hash,
                    prerequisite_hash,
                    profile_hash,
                    active_policy_hash,
                    configuration_hash,
                    prerequisites.quality.result_digest,
                    prerequisites.harmonization.result_digest,
                    *(item.evidence_digest for item in controls),
                }
            )
        ),
        configuration_digest=configuration_hash,
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=controls,
    )


def _evidence(  # noqa: PLR0913, PLR0917 - explicit evidence category closure.
    context: ExecutionContext,
    profile: IdentificationSupportProfile,
    policy: IdentificationSupportPolicy,
    prerequisites: IdentificationSupportPrerequisites,
    facts: tuple[DeclaredSupportFact, ...],
    contexts: tuple[IdentificationContextReceipt, ...],
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            reference=reference,
            role="evidence",
            claim=claim,
        )
        for reference, claim in support_route_evidence_index(
            context,
            prerequisites,
            profile,
            policy,
            facts,
            contexts,
        )
    )


__all__ = [
    "M0207_SENSITIVITY_NOTES",
    "M0207_UNCERTAINTY_RATIONALES",
    "IdentificationSupportAuthorizationError",
    "IdentificationSupportReceiptError",
    "M0207SupportRouterEngine",
    "build_identification_harmonization_support_receipt",
    "build_identification_quality_support_receipt",
    "build_identification_support_prerequisites",
    "preflight_identification_support_authorization",
    "route_identification_support",
]
