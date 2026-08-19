"""Deterministic authorization-first M17-03 fusion and aggregation engine."""

# Audit-oriented branches are intentionally kept visible.
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m17_03 import (
    M1703_CONTRACT_VERSION,
    M1703_MODULE_ID,
    DisagreementStatus,
    FuseVariantPeptideEvidenceRequest,
    FusionFinding,
    FusionFindingCode,
    FusionStatus,
    IntegratedEvidenceObject,
    ReliabilityBand,
    VariantPeptideIntegratedEvidenceResult,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
)

_REQUEST_ADAPTER: Final = TypeAdapter(FuseVariantPeptideEvidenceRequest)
_RESULT_ADAPTER: Final = TypeAdapter(VariantPeptideIntegratedEvidenceResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class M1703AuthorizationError(PermissionError):
    """Caller controls do not authorize component-specific integration."""

    def __init__(self) -> None:
        super().__init__(
            "M17-03 requires accepted controls, resolved identity, and granted consent"
        )


class M1703ReplayVerificationError(ValueError):
    """An M17-03 result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M17-03 replay verification failed")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m1703_authorization(candidate: object) -> None:
    """Check all seven controls before traversing contribution material."""

    try:
        context = _member(candidate, "context")
        refs = _member(context, "references")
        expected = {
            "approved_configuration": "accepted",
            "identity_lineage": "resolved",
            "provenance": "accepted",
            "consent": "granted",
            "quality": "accepted",
            "support": "accepted",
            "intended_use": "accepted",
        }
        states = {role: _state(_member(_member(refs, role), "state")) for role in expected}
    except Exception:  # noqa: BLE001
        raise M1703AuthorizationError from None
    if states != expected:
        raise M1703AuthorizationError


def _prepare(candidate: object) -> object:
    preflight_m1703_authorization(candidate)
    return candidate


def _evidence(request: FuseVariantPeptideEvidenceRequest) -> tuple[EvidenceReference, ...]:
    refs = request.context.references
    artifacts: list[ArtifactReference] = [
        request.alignment_result,
        request.configuration.evidence[0].reference
        if request.configuration.evidence
        else request.source_artifacts[0],
        *request.source_artifacts,
        *(item.artifact for item in request.contributions),
        *(item.reference for item in request.configuration.evidence),
        *(ev.reference for disagreement in request.disagreements for ev in disagreement.evidence),
        *(ev.reference for propagation in request.propagation for ev in propagation.evidence),
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
    ]
    unique: dict[str, ArtifactReference] = {}
    for artifact in artifacts:
        unique.setdefault(artifact.digest, artifact)
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim="Caller-declared M17-03 source attribution, reliability, and propagation evidence.",
        )
        for artifact in tuple(unique.values())[:64]
    )


def _uncertainty(*, estimable: bool) -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED if estimable else EstimateState.NOT_ESTIMABLE,
        probability=0.9 if estimable else None,
        rationale=(
            "All component-specific contributions and references are evaluable."
            if estimable
            else "At least one contribution is unsupported or not evaluable."
        ),
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
            "Scores, source claims, propagation assertions, and issuer authority are caller-declared.",
            "Unsupported or missing evidence is never converted into a negative integrated finding.",
        ),
    )


def _provenance(
    request: FuseVariantPeptideEvidenceRequest, request_digest: str
) -> ProvenanceRecord:
    refs = request.context.references
    controls = (
        (ControlRole.APPROVED_CONFIGURATION, refs.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, refs.identity_lineage),
        (ControlRole.PROVENANCE, refs.provenance),
        (ControlRole.CONSENT, refs.consent),
        (ControlRole.QUALITY, refs.quality),
        (ControlRole.SUPPORT, refs.support),
        (ControlRole.INTENDED_USE, refs.intended_use),
    )
    decisions = tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=reference.decision_id,
            state=str(_state(reference.state)),
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=getattr(reference, "binding_digest", None),
        )
        for role, reference in controls
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M1703_MODULE_ID,
        module_version=M1703_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request_digest,
            request.alignment_result.digest,
            request.configuration.evidence[0].reference.digest
            if request.configuration.evidence
            else request.source_artifacts[0].digest,
            *(item.artifact.digest for item in request.contributions),
            *(artifact.digest for artifact in request.source_artifacts),
        ),
        configuration_digest=refs.approved_configuration.evidence.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


def _classify(
    request: FuseVariantPeptideEvidenceRequest,
) -> tuple[FusionStatus, bool, tuple[FusionFindingCode, ...]]:
    findings: list[FusionFindingCode] = []
    if any(
        item.reliability_band is ReliabilityBand.NOT_EVALUABLE for item in request.contributions
    ):
        findings.append(FusionFindingCode.UNSUPPORTED_INPUT)
        findings.append(FusionFindingCode.INPUT_INCOMPLETE)
        return FusionStatus.ABSTAINED, True, tuple(findings)
    if any(item.status is DisagreementStatus.OPEN for item in request.disagreements):
        findings.append(FusionFindingCode.SOURCE_DISAGREEMENT)
    if any(item.reliability_band is ReliabilityBand.LOW for item in request.contributions):
        findings.append(FusionFindingCode.LOW_RELIABILITY)
    return FusionStatus.INTEGRATED, bool(findings), tuple(findings)


def _findings(
    codes: tuple[FusionFindingCode, ...], evidence: tuple[EvidenceReference, ...]
) -> tuple[FusionFinding, ...]:
    return tuple(
        FusionFinding(
            finding_id=f"finding.m1703.{code.value}",
            code=code,
            message={
                FusionFindingCode.SOURCE_DISAGREEMENT: "Source disagreement is retained and requires review.",
                FusionFindingCode.LOW_RELIABILITY: "A low-reliability contribution limits support.",
                FusionFindingCode.UNSUPPORTED_INPUT: "A contribution is not safely evaluable.",
                FusionFindingCode.INPUT_INCOMPLETE: "The integrated object is abstained because support is incomplete.",
            }.get(code, "Fusion finding requires explicit review."),
            evidence=evidence[:1],
        )
        for code in codes
    )


def _limitations(*, supported: bool) -> tuple[Limitation, ...]:
    values = [
        Limitation(
            code="caller_declared_fusion",
            statement="Source claims, scores, propagation assertions, and issuer authority are caller-declared.",
        ),
        Limitation(
            code="prohibited_outputs",
            statement="No generic all-omics fusion, kinase activity, treatment recommendation, or identity inference is emitted.",
        ),
    ]
    if not supported:
        values.append(
            Limitation(
                code="safe_abstention",
                statement="No integrated evidence object is published when a contribution is not evaluable.",
            )
        )
    return tuple(values)


class M1703FusionAggregationEngine:
    """Fuse attributable component contributions without erasing disagreement."""

    __slots__ = ()

    def infer(self, request: object) -> VariantPeptideIntegratedEvidenceResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
        self, request: FuseVariantPeptideEvidenceRequest
    ) -> VariantPeptideIntegratedEvidenceResult:
        request_hash = canonical_request_digest(request)
        evidence = _evidence(request)
        status, review, codes = _classify(request)
        integrated = (
            IntegratedEvidenceObject(
                integrated_id=f"integrated.{request_hash.removeprefix('sha256:')}",
                version=request.configuration.version,
                contributions=request.contributions,
                disagreements=request.disagreements,
                propagation=request.propagation,
                configuration=request.configuration,
                evidence=evidence,
            )
            if status is FusionStatus.INTEGRATED
            else None
        )
        payload: dict[str, object] = {
            "output_type": "variant_peptide_integrated_evidence",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1703_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": status,
            "integrated_evidence": integrated,
            "findings": _findings(codes, evidence),
            "abstention_reason": None
            if status is FusionStatus.INTEGRATED
            else "Fusion inputs are not safely evaluable.",
            "parent_target": "variant_peptide",
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED if not review else SupportStatus.REVIEW_REQUIRED,
                reason_code="m1703_fusion_supported" if not review else "m1703_fusion_review",
                rationale="All attributable contributions meet the declared support envelope."
                if not review
                else "Reliability, disagreement, or support limitations require human review.",
            ),
            "uncertainty": _uncertainty(estimable=status is FusionStatus.INTEGRATED),
            "provenance": _provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _limitations(supported=status is FusionStatus.INTEGRATED),
            "human_review_required": review,
        }
        constructed = VariantPeptideIntegratedEvidenceResult.model_construct(**payload)  # type: ignore[arg-type]
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self, result: object, *, replay: bool = True
    ) -> VariantPeptideIntegratedEvidenceResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1703ReplayVerificationError from error
        try:
            validated = _RESULT_ADAPTER.validate_python(
                validated.model_dump(mode="python", warnings=False), strict=True
            )
        except Exception as error:
            raise M1703ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1703ReplayVerificationError
        if replay:
            expected = self.infer(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1703ReplayVerificationError
        return validated


def fuse_variant_peptide_evidence(request: object) -> VariantPeptideIntegratedEvidenceResult:
    """Public provisional M17-03 operation."""

    return M1703FusionAggregationEngine().infer(request)


__all__ = [
    "M1703AuthorizationError",
    "M1703FusionAggregationEngine",
    "M1703ReplayVerificationError",
    "fuse_variant_peptide_evidence",
    "preflight_m1703_authorization",
]
