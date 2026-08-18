"""Replay-safe component-specific fusion for M20-03."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m20_03 import (
    M2003_CONTRACT_VERSION,
    M2003_EVIDENCE_CLAIM,
    M2003_MAX_EVIDENCE,
    M2003_MODULE_ID,
    DisagreementStatus,
    FuseProteinSubtypeEvidenceRequest,
    FusionFinding,
    FusionFindingCode,
    FusionStatus,
    IntegratedEvidenceObject,
    ProteinSubtypeIntegratedEvidenceResult,
    ReliabilityBand,
)
from glio_proteogen.contracts.m20_03.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
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

_REQUEST_ADAPTER: Final = TypeAdapter(FuseProteinSubtypeEvidenceRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinSubtypeIntegratedEvidenceResult)
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
_FORBIDDEN_TERMS: Final = frozenset(
    {"all-omics", "kinase", "treatment", "identity inference", "diagnosis"}
)


class M2003AuthorizationError(ValueError):
    """Raised before source traversal when a required control is unsafe."""


class M2003ReplayError(ValueError):
    """Raised when a result no longer binds to its exact request or payload."""


def _member(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def preflight_m2003_authorization(candidate: object) -> None:
    """Require all seven caller-declared controls before fusion traversal."""

    references = _member(_member(candidate, "context"), "references")
    if references is None:
        raise M2003AuthorizationError(  # noqa: TRY003
            "M20-03 requires all seven upstream controls"
        )
    for name, expected in _CONTROL_STATES.items():
        decision = _member(references, name)
        actual = _member(decision, "state")
        actual_value = getattr(actual, "value", actual)
        if actual_value != expected:
            raise M2003AuthorizationError(  # noqa: TRY003
                f"M20-03 control {name} must be {expected}; received {actual_value}"
            )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="M20-03 aggregates declared evidence; it does not estimate biological truth.",
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
            "Fusion is sensitive to declared reliability, source attribution, configuration, "
            "upstream compatibility, and preserved disagreement state.",
        ),
    )


def _control_decisions(
    request: FuseProteinSubtypeEvidenceRequest,
) -> tuple[ControlDecisionRecord, ...]:
    refs = request.context.references
    records: list[ControlDecisionRecord] = []
    for role, decision in (
        (ControlRole.APPROVED_CONFIGURATION, refs.approved_configuration),
        (ControlRole.PROVENANCE, refs.provenance),
        (ControlRole.QUALITY, refs.quality),
        (ControlRole.SUPPORT, refs.support),
        (ControlRole.INTENDED_USE, refs.intended_use),
    ):
        records.append(
            ControlDecisionRecord(
                role=role,
                decision_id=decision.decision_id,
                state=decision.state.value,
                policy_version=decision.policy_version,
                evidence_digest=decision.evidence.digest,
            )
        )
    records.extend(
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
    return tuple(records)


def _provenance(request: FuseProteinSubtypeEvidenceRequest) -> ProvenanceRecord:
    refs = request.context.references
    input_digests = tuple(
        dict.fromkeys(
            (
                request.alignment_result.digest,
                *(artifact.digest for artifact in request.source_artifacts),
                *(item.artifact.digest for item in request.contributions),
            )
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id=M2003_MODULE_ID,
        module_version=M2003_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=sha256_digest(request.configuration),
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=_control_decisions(request),
    )


def _evidence(request: FuseProteinSubtypeEvidenceRequest) -> tuple[EvidenceReference, ...]:
    items: list[EvidenceReference] = []
    seen: set[tuple[str, str]] = set()
    for artifact in (request.alignment_result, *request.source_artifacts):
        key = (artifact.artifact_id, artifact.digest)
        if key not in seen and len(items) < M2003_MAX_EVIDENCE:
            seen.add(key)
            items.append(
                EvidenceReference(reference=artifact, role="evidence", claim=M2003_EVIDENCE_CLAIM)
            )
    for evidence in (
        *request.configuration.evidence,
        *(item for contribution in request.contributions for item in contribution.evidence),
        *(item for disagreement in request.disagreements for item in disagreement.evidence),
    ):
        key = (evidence.reference.artifact_id, evidence.reference.digest)
        if key not in seen and len(items) < M2003_MAX_EVIDENCE:
            seen.add(key)
            items.append(evidence)
    return tuple(items)


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="component_specific_evidence_only",
            statement="M20-03 aggregates caller-declared evidence and does not infer biology.",
        ),
        Limitation(
            code="upstream_not_authenticated",
            statement="The M20-02 alignment artifact and issuer authority are not authenticated.",
        ),
        Limitation(
            code="no_kinase_treatment_or_all_omics",
            statement="Kinase, all-omics, treatment, and identity claims remain outside M20-03.",
        ),
    )


def _finding(
    request_id: str,
    code: FusionFindingCode,
    message: str,
    evidence: tuple[EvidenceReference, ...] = (),
) -> FusionFinding:
    return FusionFinding(
        finding_id=f"finding.{request_id}.{code.value}",
        code=code,
        message=message,
        evidence=evidence,
    )


def _findings(request: FuseProteinSubtypeEvidenceRequest) -> tuple[FusionFinding, ...]:
    findings: list[FusionFinding] = []
    threshold = request.configuration.reliability_threshold
    for contribution in request.contributions:
        claim = contribution.claim.casefold()
        if any(term in claim for term in _FORBIDDEN_TERMS):
            findings.append(
                _finding(
                    request.request_id,
                    FusionFindingCode.OWNERSHIP_UNCLEAR,
                    "Contribution claim exceeds the component-specific M20-03 authority boundary.",
                    contribution.evidence,
                )
            )
        if contribution.reliability_band is ReliabilityBand.NOT_EVALUABLE:
            findings.append(
                _finding(
                    request.request_id,
                    FusionFindingCode.INPUT_INCOMPLETE,
                    "A source contribution has no evaluable reliability state.",
                    contribution.evidence,
                )
            )
        elif contribution.reliability_score < threshold:
            findings.append(
                _finding(
                    request.request_id,
                    FusionFindingCode.LOW_RELIABILITY,
                    "A source contribution is below the locked reliability threshold.",
                    contribution.evidence,
                )
            )
    findings.extend(
        _finding(
            request.request_id,
            FusionFindingCode.SOURCE_DISAGREEMENT,
            "An unresolved or non-evaluable source disagreement requires review.",
            disagreement.evidence,
        )
        for disagreement in request.disagreements
        if disagreement.status is not DisagreementStatus.RESOLVED
    )
    return tuple(findings)


class M2003Engine:
    """Fuse attributable evidence while preserving reliability and disagreement."""

    def validate_request(self, candidate: object) -> FuseProteinSubtypeEvidenceRequest:
        preflight_m2003_authorization(candidate)
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)

    def fuse(self, candidate: object) -> ProteinSubtypeIntegratedEvidenceResult:
        request = self.validate_request(candidate)
        request_digest = canonical_request_digest(request)
        findings = _findings(request)
        evidence = _evidence(request)
        if findings:
            status = FusionStatus.ABSTAINED
            integrated = None
            support = SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="fusion_safety_boundary",
                rationale=(
                    "No integrated object is emitted while reliability, ownership, or "
                    "disagreement controls fail."
                ),
            )
            abstention_reason = (
                "Fusion abstained on a reliability, ownership, or disagreement control."
            )
        else:
            status = FusionStatus.INTEGRATED
            integrated = IntegratedEvidenceObject(
                integrated_id=f"integrated.{request.request_id}",
                version=request.configuration.version,
                aggregate_claim="Component-specific integrated protein subtype evidence.",
                contributions=request.contributions,
                disagreements=request.disagreements,
                aggregate_values=request.aggregate_values,
                configuration=request.configuration,
                evidence=evidence,
            )
            support = SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="component_specific_fusion_complete",
                rationale=(
                    "Attributable source contributions satisfy the declared reliability policy."
                ),
            )
            abstention_reason = None
        payload: dict[str, Any] = {
            "output_type": "protein_subtype_integrated_evidence",
            "result_id": f"result.{request.request_id}",
            "result_version": M2003_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": status,
            "integrated_evidence": integrated,
            "findings": findings,
            "abstention_reason": abstention_reason,
            "parent_target": "protein subtype",
            "emits_parent": False,
            "support_decision": support,
            "uncertainty": _uncertainty(),
            "provenance": _provenance(request),
            "evidence": evidence,
            "limitations": _limitations(),
            "human_review_required": bool(findings),
        }
        payload["result_digest"] = result_payload_digest(
            ProteinSubtypeIntegratedEvidenceResult.model_construct(**payload)
        )
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def replay(
        self,
        result: ProteinSubtypeIntegratedEvidenceResult,
    ) -> ProteinSubtypeIntegratedEvidenceResult:
        request_digest_matches = result.request_digest == canonical_request_digest(result.request)
        payload_digest_matches = result.result_digest == result_payload_digest(result)
        if not request_digest_matches:
            raise M2003ReplayError(  # noqa: TRY003
                "M20-03 result request digest mismatch"
            )
        if not payload_digest_matches:
            raise M2003ReplayError(  # noqa: TRY003
                "M20-03 result payload digest mismatch"
            )
        validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        expected = self.fuse(validated.request)
        if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
            raise M2003ReplayError(  # noqa: TRY003
                "M20-03 deterministic replay result mismatch"
            )
        return validated


def fuse_protein_subtype_evidence(candidate: object) -> ProteinSubtypeIntegratedEvidenceResult:
    return M2003Engine().fuse(candidate)


__all__ = [
    "M2003AuthorizationError",
    "M2003Engine",
    "M2003ReplayError",
    "fuse_protein_subtype_evidence",
    "preflight_m2003_authorization",
]
