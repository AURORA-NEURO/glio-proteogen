"""Pure contract-facing deterministic support router for M01-07."""

from __future__ import annotations

from collections.abc import Mapping
from itertools import chain
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_07 import (
    CriterionAssessment,
    CriterionDecision,
    RouteDecision,
    RouteSupportRequest,
    SupportRoutingResult,
    canonical_request_digest,
    configuration_digest,
    policy_digest,
    profile_digest,
)
from glio_proteogen.contracts.m01_07.v1 import M0107_CONTRACT_VERSION, M0107_MODULE_ID
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
from glio_proteogen.modules.c01_preanalytic.m01_07_support_router.kernel import (
    Criterion,
    CriterionKind,
    EvidenceState,
    EvidenceValue,
    route_support,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

_REQUEST_ADAPTER: Final[TypeAdapter[RouteSupportRequest]] = TypeAdapter(RouteSupportRequest)
_AUTHORIZATION_MESSAGE: Final = "support routing requires accepted upstream authorization states"
_DIMENSION_ORDER: Final = {
    "assay": 0,
    "specimen": 1,
    "disease_class": 2,
    "quality": 3,
    "completeness": 4,
    "platform": 5,
    "reference": 6,
    "intended_use": 7,
}
_LIMITATIONS: Final = (
    Limitation(
        code="support_routing_only",
        statement=(
            "This result routes declared support-domain evidence only; it is not a negative "
            "scientific finding, proteotype, kinase state, clinical claim, or treatment advice."
        ),
    ),
    Limitation(
        code="external_controls_unverified",
        statement=(
            "Upstream controls, criteria, and evidence references are caller-declared and "
            "their issuers are not authenticated by M01-07."
        ),
    ),
)


class SupportRoutingAuthorizationError(ValueError):
    """Raw request authorization failed before support evidence was parsed."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class M0107SupportRouter:
    """Route one immutable request without I/O, persistence, or learned inference."""

    __slots__ = ()

    def route(self, request: RouteSupportRequest) -> SupportRoutingResult:
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        preflight_support_routing_authorization(validated)
        request_hash = canonical_request_digest(validated)
        profile_hash = profile_digest(validated.profile)
        active_policy_hash = policy_digest(validated.policy)
        configuration_hash = configuration_digest(validated.profile, validated.policy)
        assessments = _assessments(validated)
        decision = (
            RouteDecision.ABSTAINED
            if any(item.blocks_route for item in assessments)
            else RouteDecision.SUPPORTED
        )
        return SupportRoutingResult(
            routing_id=f"routing.m0107.{request_hash.removeprefix('sha256:')}",
            request_digest=request_hash,
            profile_digest=profile_hash,
            policy_digest=active_policy_hash,
            configuration_digest=configuration_hash,
            decision=decision,
            assessments=assessments,
            support=_support(decision),
            uncertainty=_uncertainty(),
            provenance=_provenance(
                validated,
                (request_hash, profile_hash, active_policy_hash, configuration_hash),
            ),
            evidence=_evidence(validated),
            limitations=_LIMITATIONS,
            human_review_required=decision is RouteDecision.ABSTAINED,
            completed_at=validated.context.occurred_at,
            supersedes_result_digest=validated.supersedes_result_digest,
        )


def route_support_request(request: RouteSupportRequest) -> SupportRoutingResult:
    """Convenience entry point for stateless callers and agent tools."""

    return M0107SupportRouter().route(request)


def preflight_support_routing_authorization(candidate: object) -> None:
    """Reject unauthorized raw requests before accessing evidence payloads."""

    if isinstance(candidate, RouteSupportRequest):
        context: object = candidate.context
    elif isinstance(candidate, Mapping):
        context = candidate.get("context")
    else:
        raise SupportRoutingAuthorizationError
    references = _value(context, "references")
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
        _value(_value(references, role), "state") != state
        for role, state in expected.items()
    ):
        raise SupportRoutingAuthorizationError


def _value(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _assessments(request: RouteSupportRequest) -> tuple[CriterionAssessment, ...]:
    evidence = {item.evidence_id: item for item in request.evidence}
    criteria = tuple(
        sorted(
            request.profile.criteria,
            key=lambda item: (_DIMENSION_ORDER[item.dimension.value], item.criterion_id),
        )
    )
    kernel_criteria = tuple(
        Criterion(
            criterion_id=item.criterion_id,
            signal_id=item.evidence_id,
            kind=CriterionKind(item.kind.value),
            remediation_code=item.remediation_code,
            required=item.required,
            allow_not_applicable=item.allow_not_applicable,
            allowed_terms=item.allowed_terms,
            minimum=item.minimum,
            maximum=item.maximum,
            expected_bool=item.expected_bool,
        )
        for item in criteria
    )
    kernel_evidence = {
        item.evidence_id: EvidenceValue(
            state=EvidenceState(item.state.value),
            value=item.value,
        )
        for item in request.evidence
    }
    routed = route_support(kernel_criteria, kernel_evidence)
    results = {item.criterion_id: item for item in routed.criteria}
    return tuple(
        CriterionAssessment(
            criterion_id=criterion.criterion_id,
            dimension=criterion.dimension,
            required=criterion.required,
            allow_not_applicable=criterion.allow_not_applicable,
            evidence_state=evidence[criterion.evidence_id].state,
            decision=CriterionDecision(results[criterion.criterion_id].decision.value),
            blocks_route=results[criterion.criterion_id].decision.value != "supported",
            reason_code=(
                None
                if results[criterion.criterion_id].decision.value == "supported"
                else criterion.reason_code
            ),
            remediation_code=(
                None
                if results[criterion.criterion_id].decision.value == "supported"
                else criterion.remediation_code
            ),
            remediation_path=(
                None
                if results[criterion.criterion_id].decision.value == "supported"
                else criterion.remediation_path
            ),
            evidence_digests=tuple(
                sorted({item.digest for item in evidence[criterion.evidence_id].evidence})
            ),
        )
        for criterion in criteria
    )


def _support(decision: RouteDecision) -> SupportDecision:
    if decision is RouteDecision.ABSTAINED:
        return SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED,
            reason_code="support_domain_abstained",
            rationale="At least one support criterion requires abstention or review.",
        )
    return SupportDecision(
        status=SupportStatus.SUPPORTED,
        reason_code="support_domain_supported",
        rationale="Every blocking support criterion is satisfied in the declared domain.",
    )


def _not_estimable(rationale: str) -> UncertaintyEstimate:
    return UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=rationale)


def _uncertainty() -> UncertaintyProfile:
    return UncertaintyProfile(
        measurement=_not_estimable("Support evidence measurement uncertainty was not supplied."),
        sampling=_not_estimable("No sampling distribution was supplied."),
        parameter=_not_estimable("Reviewed routing predicates have no fitted parameters."),
        model_form=_not_estimable("No learned model is used."),
        identification=_not_estimable("Residual evidence attribution error is not scored."),
        support=_not_estimable("Support is a deterministic routing state."),
        transport=_not_estimable("Transport beyond the declared profile is not estimated."),
        sensitivity_notes=(
            "Missing and unknown evidence are indeterminate and never interpreted as negative.",
            "Observed unsupported evidence abstains even when its criterion is optional.",
        ),
    )


def _control_records(context: ExecutionContext) -> tuple[ControlDecisionRecord, ...]:
    references = context.references
    controls = (
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
            subject_digest=subject_digest,
        )
        for role, reference, subject_digest in controls
    )


def _provenance(
    request: RouteSupportRequest,
    envelope_hashes: tuple[str, str, str, str],
) -> ProvenanceRecord:
    request_hash, profile_hash, active_policy_hash, configuration_hash = envelope_hashes
    references = request.context.references
    controls = _control_records(request.context)
    return ProvenanceRecord(
        activity_id=f"activity.m0107.{request_hash.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0107_MODULE_ID,
        module_version=M0107_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(
            sorted(
                {
                    request_hash,
                    profile_hash,
                    active_policy_hash,
                    configuration_hash,
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


def _evidence(request: RouteSupportRequest) -> tuple[EvidenceReference, ...]:
    references = request.context.references
    controls = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration.evidence),
        (ControlRole.IDENTITY_LINEAGE, references.identity_lineage.evidence),
        (ControlRole.PROVENANCE, references.provenance.evidence),
        (ControlRole.CONSENT, references.consent.evidence),
        (ControlRole.QUALITY, references.quality.evidence),
        (ControlRole.SUPPORT, references.support.evidence),
        (ControlRole.INTENDED_USE, references.intended_use.evidence),
    )
    control_evidence = tuple(
        EvidenceReference(
            reference=reference,
            role="evidence",
            claim=f"Caller-declared {role.value.replace('_', '-')} control reference.",
        )
        for role, reference in controls
    )
    artifacts = _bounded_references(
        chain(
            (request.profile.evidence,),
            (item for value in request.evidence for item in value.evidence),
        ),
        limit=505,
    )
    routed_evidence = tuple(
        EvidenceReference(
            reference=item,
            role="evidence",
            claim="Caller-declared support evidence; the source payload is not retained.",
        )
        for item in artifacts
    )
    return (*control_evidence, *routed_evidence)


def _bounded_references(
    references: Iterable[ArtifactReference],
    *,
    limit: int,
) -> tuple[ArtifactReference, ...]:
    return tuple(sorted(set(references), key=canonical_json_bytes)[:limit])


__all__ = [
    "M0107SupportRouter",
    "SupportRoutingAuthorizationError",
    "preflight_support_routing_authorization",
    "route_support_request",
]
