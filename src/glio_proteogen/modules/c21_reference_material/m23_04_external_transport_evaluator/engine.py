"""Deterministic caller-declared M23-04 external transport runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m23_04 import (
    M2304_CONTRACT_VERSION,
    M2304_EVIDENCE_CLAIM,
    M2304_MODULE_ID,
    EvaluateVariantPeptideExternalTransportRequest,
    EvaluationStatus,
    SupportDomainUpdate,
    TransportabilityReport,
    TransportFinding,
    TransportFindingCode,
    TransportStatus,
    VariantPeptideExternalTransportResult,
    canonical_request_digest,
    result_identifier,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentState,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    IdentityLineageReference,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateVariantPeptideExternalTransportRequest)
_RESULT_ADAPTER: Final = TypeAdapter(VariantPeptideExternalTransportResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class M2304AuthorizationError(ValueError):
    """Caller-declared controls do not authorize transport evaluation."""

    def __init__(self) -> None:
        super().__init__(
            "M23-04 transport evaluation requires accepted configuration, resolved identity, "
            "granted consent, and accepted provenance/quality/support/intended-use controls"
        )


class M2304ReplayError(ValueError):
    """A transport result failed canonical replay verification."""


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state(candidate: object) -> object:
    value = _member(candidate, "state")
    return getattr(value, "value", value)


def preflight_m2304_authorization(candidate: object) -> None:
    """Reject denied controls before reading caller-declared transport material."""

    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        expected = {
            "approved_configuration": UpstreamDecisionState.ACCEPTED.value,
            "identity_lineage": "resolved",
            "provenance": UpstreamDecisionState.ACCEPTED.value,
            "consent": ConsentState.GRANTED.value,
            "quality": UpstreamDecisionState.ACCEPTED.value,
            "support": UpstreamDecisionState.ACCEPTED.value,
            "intended_use": UpstreamDecisionState.ACCEPTED.value,
        }
        authorized = all(
            _state(_member(references, role)) == value for role, value in expected.items()
        )
    except Exception:  # noqa: BLE001 - hostile mappings fail closed.
        raise M2304AuthorizationError from None
    if not authorized:
        raise M2304AuthorizationError


def _evidence(
    request: EvaluateVariantPeptideExternalTransportRequest,
) -> tuple[EvidenceReference, ...]:
    artifacts: list[ArtifactReference] = [
        request.mass_spectrometry_proteome,
        request.genome_transcriptome,
        request.ptm_annotations,
        request.benchmark_package,
        *request.source_artifacts,
        *(validation.provenance_artifact for validation in request.validations),
        *(item.reference for validation in request.validations for item in validation.evidence),
        *(item.reference for evaluation in request.evaluations for item in evaluation.evidence),
        *(item.reference for item in request.configuration.evidence),
    ]
    unique: dict[str, ArtifactReference] = {}
    for artifact in artifacts:
        unique.setdefault(artifact.digest, artifact)
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M2304_EVIDENCE_CLAIM)
        for artifact in tuple(unique.values())[:64]
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=(
                f"M23-04 does not estimate {dimension} uncertainty from "
                "caller-declared transport inputs."
            ),
        )

    return UncertaintyProfile(
        measurement=unavailable("measurement"),
        sampling=unavailable("sampling"),
        parameter=unavailable("parameter"),
        model_form=unavailable("model form"),
        identification=unavailable("identification"),
        support=unavailable("support"),
        transport=unavailable("transport"),
        sensitivity_notes=(
            "Transport metrics, calibration floors, and issuer authority are caller-declared.",
            "External transport evidence is not a variant-peptide or treatment recommendation.",
        ),
    )


def _provenance(
    request: EvaluateVariantPeptideExternalTransportRequest, request_digest: str
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
            decision_id=decision.decision_id,
            state=str(_state(decision)),
            policy_version=decision.policy_version,
            evidence_digest=decision.evidence.digest,
            subject_digest=(
                decision.binding_digest if isinstance(decision, IdentityLineageReference) else None
            ),
        )
        for role, decision in controls
    )
    return ProvenanceRecord(
        activity_id=f"m2304.activity.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M2304_MODULE_ID,
        module_version=M2304_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(
            dict.fromkeys(
                (
                    request_digest,
                    request.mass_spectrometry_proteome.digest,
                    request.genome_transcriptome.digest,
                    request.ptm_annotations.digest,
                    request.benchmark_package.digest,
                    *(artifact.digest for artifact in request.source_artifacts),
                )
            )
        ),
        configuration_digest=refs.approved_configuration.evidence.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


def _finding(
    code: TransportFindingCode,
    message: str,
    evidence: tuple[EvidenceReference, ...],
) -> TransportFinding:
    return TransportFinding(
        finding_id=f"finding.m2304.{code.value}",
        code=code,
        message=message,
        evidence=evidence[:1],
    )


def _findings(
    request: EvaluateVariantPeptideExternalTransportRequest,
    evidence: tuple[EvidenceReference, ...],
) -> tuple[TransportFinding, ...]:
    findings: list[TransportFinding] = []
    if any(item.status is TransportStatus.DOMAIN_NARROWED for item in request.evaluations):
        findings.append(
            _finding(
                TransportFindingCode.SUPPORT_DOMAIN_NARROWED,
                "Support domain was narrowed for one or more transport dimensions.",
                evidence,
            )
        )
    if any(item.metric_value < item.calibration_floor for item in request.evaluations):
        findings.append(
            _finding(
                TransportFindingCode.CALIBRATION_FLOOR_FAILED,
                "A caller-declared calibration floor was not met.",
                evidence,
            )
        )
    if any(
        item.dimension.value == "specimen" and item.status is TransportStatus.DOMAIN_NARROWED
        for item in request.evaluations
    ):
        findings.append(
            _finding(
                TransportFindingCode.SPECIMEN_MISMATCH,
                "Specimen transport requires explicit support-domain review.",
                evidence,
            )
        )
    if not findings:
        findings.append(
            _finding(
                TransportFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                "The provisional ABI requires governed owner review.",
                evidence,
            )
        )
    return tuple(findings)


def _report(
    request: EvaluateVariantPeptideExternalTransportRequest,
    request_digest: str,
    evidence: tuple[EvidenceReference, ...],
) -> TransportabilityReport:
    narrowed = tuple(
        item.dimension
        for item in request.evaluations
        if item.status is TransportStatus.DOMAIN_NARROWED
    )
    retained = tuple(
        item.dimension
        for item in request.evaluations
        if item.status is not TransportStatus.DOMAIN_NARROWED
    )
    support_status = TransportStatus.DOMAIN_NARROWED if narrowed else TransportStatus.SUPPORTED
    return TransportabilityReport(
        report_id=f"report.m2304.{request_digest.removeprefix('sha256:')}",
        version=request.configuration.version,
        validations=request.validations,
        evaluations=request.evaluations,
        support_domain=SupportDomainUpdate(
            update_id=f"support.m2304.{request_digest.removeprefix('sha256:')}",
            version=request.configuration.version,
            status=support_status,
            retained_dimensions=retained or (narrowed[0],),
            narrowed_dimensions=narrowed,
            rationale=(
                "All configured dimensions meet the declared calibration floor."
                if not narrowed
                else "Dimensions below the declared floor remain explicit and narrowed."
            ),
            evidence=evidence[:1],
        ),
        configuration=request.configuration,
        evidence=evidence,
    )


def _limitations(*, abstained: bool) -> tuple[Limitation, ...]:
    values = [
        Limitation(
            code="caller_declared_transport",
            statement=(
                "Transport validations, metrics, floors, and issuer authority are caller-declared."
            ),
        ),
        Limitation(
            code="prohibited_outputs",
            statement=(
                "No variant-peptide estimate, kinase activity, all-omics fusion, treatment "
                "recommendation, identity inference, or consent inference is emitted."
            ),
        ),
    ]
    if abstained:
        values.append(
            Limitation(
                code="safe_abstention",
                statement=(
                    "Incomplete or non-evaluable transport dimensions produce no transport report."
                ),
            )
        )
    return tuple(values)


class M2304Engine:
    """Evaluate caller-declared external transport with safe abstention."""

    __slots__ = ()

    def evaluate(self, request: object) -> VariantPeptideExternalTransportResult:
        preflight_m2304_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        return self._result(validated)

    def _result(
        self, request: EvaluateVariantPeptideExternalTransportRequest
    ) -> VariantPeptideExternalTransportResult:
        request_digest = canonical_request_digest(request)
        evidence = _evidence(request)
        no_evaluable_dimension = any(
            item.status is TransportStatus.NOT_EVALUABLE for item in request.evaluations
        )
        no_retained_domain = all(
            item.status is TransportStatus.DOMAIN_NARROWED for item in request.evaluations
        )
        abstained = no_evaluable_dimension or no_retained_domain
        report = None if abstained else _report(request, request_digest, evidence)
        findings = (
            (
                _finding(
                    TransportFindingCode.EVALUATION_INCOMPLETE,
                    (
                        "One or more transport dimensions are not evaluable."
                        if no_evaluable_dimension
                        else "No retained external transport support domain remains."
                    ),
                    evidence,
                ),
            )
            if abstained
            else _findings(request, evidence)
        )
        payload: dict[str, Any] = {
            "output_type": "variant_peptide_external_transport",
            "result_id": result_identifier(request_digest),
            "result_version": M2304_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": EvaluationStatus.ABSTAINED if abstained else EvaluationStatus.EVALUATED,
            "report": report,
            "findings": findings,
            "abstention_reason": (
                (
                    "External transport dimensions are not safely evaluable."
                    if no_evaluable_dimension
                    else "No retained external transport support domain remains."
                )
                if abstained
                else None
            ),
            "parent_target": "variant peptide",
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED if abstained else SupportStatus.SUPPORTED,
                reason_code=(
                    "m2304_transport_abstained" if abstained else "m2304_transport_evaluated"
                ),
                rationale=(
                    "At least one transport dimension is not evaluable; review is required."
                    if abstained
                    else "All configured transport dimensions are independently represented."
                ),
            ),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(request, request_digest),
            "evidence": evidence,
            "limitations": _limitations(abstained=abstained),
            "human_review_required": True,
        }
        provisional = VariantPeptideExternalTransportResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(provisional)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def replay(
        self, result: VariantPeptideExternalTransportResult
    ) -> VariantPeptideExternalTransportResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
            if validated.request_digest != canonical_request_digest(validated.request):
                raise M2304ReplayError  # noqa: TRY301
            if validated.result_id != result_identifier(validated.request_digest):
                raise M2304ReplayError  # noqa: TRY301
            if validated.result_digest != result_payload_digest(validated):
                raise M2304ReplayError  # noqa: TRY301
            expected = self.evaluate(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M2304ReplayError  # noqa: TRY301
        except M2304ReplayError:
            raise
        except Exception as error:
            raise M2304ReplayError from error
        return validated


def evaluate_variant_peptide_external_transport(
    request: object,
) -> VariantPeptideExternalTransportResult:
    """Public stateless M23-04 transport evaluation entry point."""

    return M2304Engine().evaluate(request)


__all__ = [
    "M2304AuthorizationError",
    "M2304Engine",
    "M2304ReplayError",
    "evaluate_variant_peptide_external_transport",
    "preflight_m2304_authorization",
]
