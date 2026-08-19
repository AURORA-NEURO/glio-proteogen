"""Deterministic, replay-safe M20-02 source alignment engine.

Only caller-declared typed metadata is consumed.  The engine never traverses
raw artifacts, infers identity or consent, or erases conflicts.  Any missing,
conflicting, unsupported, or not-evaluable dimension is represented as a safe
abstention requiring review.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m20_02 import (
    M2002_CONTRACT_VERSION,
    M2002_MODULE_ID,
    AlignedEvidenceBundle,
    AlignmentFinding,
    AlignmentFindingCode,
    AlignmentObservationStatus,
    AlignmentStatus,
    AlignProteinSubtypeSourcesRequest,
    ProteinSubtypeAlignmentResult,
)
from glio_proteogen.contracts.m20_02.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ConsentState,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)

_REQUEST_ADAPTER: Final = TypeAdapter(AlignProteinSubtypeSourcesRequest)
_ZERO_DIGEST: Final = "sha256:" + "0" * 64
_CONTROL_STATES: Final = {
    "approved_configuration": UpstreamDecisionState.ACCEPTED.value,
    "identity_lineage": IdentityLineageState.RESOLVED.value,
    "provenance": UpstreamDecisionState.ACCEPTED.value,
    "consent": ConsentState.GRANTED.value,
    "quality": UpstreamDecisionState.ACCEPTED.value,
    "support": UpstreamDecisionState.ACCEPTED.value,
    "intended_use": UpstreamDecisionState.ACCEPTED.value,
}


class M2002AuthorizationError(ValueError):
    """Raised before typed source reconciliation when a control is unsafe."""


class M2002ReplayError(ValueError):
    """Raised when a result no longer binds to its exact request or payload."""


def _member(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def preflight_m2002_authorization(candidate: object) -> None:
    """Require all seven caller-declared controls before source traversal."""

    references = _member(_member(candidate, "context"), "references")
    if references is None:
        raise M2002AuthorizationError("M20-02 requires all seven upstream controls")  # noqa: TRY003
    for name, expected in _CONTROL_STATES.items():
        decision = _member(references, name)
        actual = _member(decision, "state")
        actual_value = getattr(actual, "value", actual)
        if actual_value != expected:
            raise M2002AuthorizationError(  # noqa: TRY003
                f"M20-02 control {name} must be {expected}; received {actual_value}"
            )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="M20-02 reconciles declared dimensions; it does not estimate biology.",
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=(
            "Alignment is sensitive to caller-declared sample, time, territory, analyte, "
            "modality, reference, and biological-context values.",
        ),
    )


def _control_decisions(
    request: AlignProteinSubtypeSourcesRequest,
) -> tuple[ControlDecisionRecord, ...]:
    refs = request.context.references
    decisions: list[ControlDecisionRecord] = []
    for role, decision in (
        (ControlRole.APPROVED_CONFIGURATION, refs.approved_configuration),
        (ControlRole.PROVENANCE, refs.provenance),
        (ControlRole.QUALITY, refs.quality),
        (ControlRole.SUPPORT, refs.support),
        (ControlRole.INTENDED_USE, refs.intended_use),
    ):
        decisions.append(
            ControlDecisionRecord(
                role=role,
                decision_id=decision.decision_id,
                state=decision.state.value,
                policy_version=decision.policy_version,
                evidence_digest=decision.evidence.digest,
            )
        )
    decisions.extend(
        (
            ControlDecisionRecord(
                role=ControlRole.IDENTITY_LINEAGE,
                decision_id=refs.identity_lineage.decision_id,
                state=refs.identity_lineage.state.value,
                policy_version=refs.identity_lineage.policy_version,
                evidence_digest=refs.identity_lineage.evidence.digest,
                subject_digest=refs.identity_lineage.binding_digest,
            ),
            ControlDecisionRecord(
                role=ControlRole.CONSENT,
                decision_id=refs.consent.decision_id,
                state=refs.consent.state.value,
                policy_version=refs.consent.policy_version,
                evidence_digest=refs.consent.evidence.digest,
            ),
        )
    )
    return tuple(decisions)


def _provenance(request: AlignProteinSubtypeSourcesRequest) -> ProvenanceRecord:
    refs = request.context.references
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id=M2002_MODULE_ID,
        module_version=M2002_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request.upstream_result.digest,
            *(artifact.digest for artifact in request.source_artifacts),
        ),
        configuration_digest=sha256_digest(request.configuration),
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=_control_decisions(request),
    )


def _evidence(request: AlignProteinSubtypeSourcesRequest) -> tuple[EvidenceReference, ...]:
    seen: set[str] = set()
    values: list[EvidenceReference] = []
    for artifact in (request.upstream_result, *request.source_artifacts):
        if artifact.digest not in seen:
            seen.add(artifact.digest)
            values.append(
                EvidenceReference(
                    reference=artifact,
                    role="evidence",
                    claim=(
                        "Caller-declared M20-02 alignment input; issuer authority is not "
                        "authenticated."
                    ),
                )
            )
    return tuple(values)


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="caller_declared_alignment_only",
            statement="The engine reconciles typed declarations and never opens source artifacts.",
        ),
        Limitation(
            code="no_identity_or_consent_inference",
            statement=(
                "Identity, consent, provenance, and intended use are not inferred or mutated."
            ),
        ),
        Limitation(
            code="conflicts_preserved",
            statement=(
                "Conflicting dimensions remain visible in the discrepancy map and abstain safely."
            ),
        ),
        Limitation(
            code="no_biological_claim",
            statement=(
                "The result does not emit a protein subtype, kinase, treatment, or all-omics claim."
            ),
        ),
    )


def _findings(request: AlignProteinSubtypeSourcesRequest) -> tuple[AlignmentFinding, ...]:
    values: list[AlignmentFinding] = []
    for observation in request.observations:
        if observation.status is AlignmentObservationStatus.CONFLICTED:
            values.append(
                AlignmentFinding(
                    finding_id=f"finding.{request.request_id}.{observation.observation_id}",
                    code=AlignmentFindingCode.DIMENSION_CONFLICT,
                    message=f"Dimension {observation.dimension.value} contains conflicting values.",
                    evidence=observation.evidence,
                )
            )
        elif observation.status is AlignmentObservationStatus.NOT_EVALUABLE:
            values.append(
                AlignmentFinding(
                    finding_id=f"finding.{request.request_id}.{observation.observation_id}",
                    code=AlignmentFindingCode.INPUT_INCOMPLETE,
                    message=f"Dimension {observation.dimension.value} is not evaluable.",
                    evidence=observation.evidence,
                )
            )
    values.extend(
        AlignmentFinding(
            finding_id=f"finding.{request.request_id}.{discrepancy.discrepancy_id}",
            code=AlignmentFindingCode.DISCREPANCY_UNRESOLVED,
            message=f"Discrepancy in {discrepancy.dimension.value} requires review.",
            evidence=discrepancy.evidence,
        )
        for discrepancy in request.discrepancies
        if discrepancy.resolution is None
    )
    return tuple(values)


class M2002Engine:
    """Reconcile one strict request with deterministic safe abstention."""

    def validate_request(self, candidate: object) -> AlignProteinSubtypeSourcesRequest:
        preflight_m2002_authorization(candidate)
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)

    def resolve(self, candidate: object) -> ProteinSubtypeAlignmentResult:
        request = self.validate_request(candidate)
        request_digest = canonical_request_digest(request)
        findings = _findings(request)
        dimensions = {item.dimension for item in request.observations}
        complete = (
            dimensions == set(request.configuration.required_dimensions)
            and len(dimensions) == len(request.observations)
            and all(
                item.status is AlignmentObservationStatus.ALIGNED for item in request.observations
            )
            and all(item.resolution is not None for item in request.discrepancies)
        )
        bundle = (
            AlignedEvidenceBundle(
                bundle_id=f"bundle.{request.request_id}",
                version=M2002_CONTRACT_VERSION,
                source_artifacts=request.source_artifacts,
                observations=request.observations,
                discrepancies=request.discrepancies,
                configuration=request.configuration,
                evidence=_evidence(request),
            )
            if complete
            else None
        )
        status = AlignmentStatus.ALIGNED if complete else AlignmentStatus.ABSTAINED
        support = SupportDecision(
            status=SupportStatus.SUPPORTED if complete else SupportStatus.REVIEW_REQUIRED,
            reason_code="aligned_sources" if complete else "alignment_review_required",
            rationale=(
                "All seven dimensions are aligned under the locked configuration."
                if complete
                else "Missing, conflicting, or unresolved dimensions require safe review."
            ),
        )
        payload: dict[str, Any] = {
            "output_type": "protein_subtype_alignment",
            "result_id": f"result.{request_digest.removeprefix('sha256:')}",
            "result_version": M2002_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": status,
            "aligned_bundle": bundle,
            "findings": findings,
            "abstention_reason": None
            if complete
            else "Alignment is incomplete or contains unresolved conflict.",
            "parent_target": "protein subtype",
            "emits_parent": False,
            "support_decision": support,
            "uncertainty": _uncertainty(),
            "provenance": _provenance(request),
            "evidence": _evidence(request),
            "limitations": _limitations(),
            "human_review_required": not complete,
        }
        payload["result_digest"] = result_payload_digest(
            ProteinSubtypeAlignmentResult.model_construct(**payload)
        )
        return ProteinSubtypeAlignmentResult.model_validate(payload, strict=True)

    def replay(self, result: ProteinSubtypeAlignmentResult) -> ProteinSubtypeAlignmentResult:
        if result.request_digest != canonical_request_digest(result.request):
            raise M2002ReplayError("M20-02 result request digest mismatch")  # noqa: TRY003
        if result.result_id != f"result.{result.request_digest.removeprefix('sha256:')}":
            raise M2002ReplayError("M20-02 result identifier mismatch")  # noqa: TRY003
        if result.result_digest != result_payload_digest(result):
            raise M2002ReplayError("M20-02 result payload digest mismatch")  # noqa: TRY003
        try:
            validated = ProteinSubtypeAlignmentResult.model_validate_json(
                canonical_json_bytes(result), strict=True
            )
            expected = self.resolve(validated.request)
        except M2002ReplayError:
            raise
        except Exception as error:
            raise M2002ReplayError("M20-02 replay result validation failed") from error  # noqa: TRY003
        if canonical_json_bytes(expected) != canonical_json_bytes(validated):
            raise M2002ReplayError("M20-02 deterministic replay mismatch")  # noqa: TRY003
        return validated


def reconcile_protein_subtype_sources(candidate: object) -> ProteinSubtypeAlignmentResult:
    """Reconcile caller-declared cross-source alignment metadata."""

    return M2002Engine().resolve(candidate)


__all__ = [
    "M2002AuthorizationError",
    "M2002Engine",
    "M2002ReplayError",
    "preflight_m2002_authorization",
    "reconcile_protein_subtype_sources",
]
