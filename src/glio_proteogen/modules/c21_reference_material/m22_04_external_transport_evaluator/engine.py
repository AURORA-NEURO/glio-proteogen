"""Deterministic caller-declared M22-04 external transport runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m22_04 import (
    M2204_CONTRACT_VERSION,
    M2204_EVIDENCE_CLAIM,
    M2204_MODULE_ID,
    EvaluateProteinRnaDiscordanceExternalTransportRequest,
    EvaluationStatus,
    ProteinRnaDiscordanceExternalTransportResult,
    SupportDomainUpdate,
    TransportabilityReport,
    TransportFinding,
    TransportFindingCode,
    TransportStatus,
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
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateProteinRnaDiscordanceExternalTransportRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinRnaDiscordanceExternalTransportResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class M2204AuthorizationError(ValueError):
    """Caller-declared controls do not authorize transport evaluation."""

    def __init__(self) -> None:
        super().__init__(
            "M22-04 transport evaluation requires accepted configuration, resolved identity, "
            "granted consent, and accepted provenance/quality/support/intended-use controls"
        )


class M2204ReplayError(ValueError):
    """A transport result failed canonical replay verification."""


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state(candidate: object) -> object:
    value = _member(candidate, "state")
    return getattr(value, "value", value)


def preflight_m2204_authorization(candidate: object) -> None:
    """Reject denied controls before reading transport validation material."""

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
        raise M2204AuthorizationError from None
    if not authorized:
        raise M2204AuthorizationError


def _evidence(
    request: EvaluateProteinRnaDiscordanceExternalTransportRequest,
) -> tuple[EvidenceReference, ...]:
    artifacts: list[ArtifactReference] = [
        request.benchmark_package,
        request.upstream_truth,
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
        EvidenceReference(reference=artifact, role="evidence", claim=M2204_EVIDENCE_CLAIM)
        for artifact in tuple(unique.values())[:64]
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=(
                f"M22-04 does not estimate {dimension} uncertainty from "
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
            "External transport evidence is not a subtype, kinase, treatment, or identity claim.",
        ),
    )


def _provenance(
    request: EvaluateProteinRnaDiscordanceExternalTransportRequest, request_digest: str
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
            subject_digest=getattr(decision, "binding_digest", None),
        )
        for role, decision in controls
    )
    return ProvenanceRecord(
        activity_id=f"m2204.activity.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M2204_MODULE_ID,
        module_version=M2204_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(
            dict.fromkeys(
                (
                    request_digest,
                    request.benchmark_package.digest,
                    request.upstream_truth.digest,
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


def _findings(
    request: EvaluateProteinRnaDiscordanceExternalTransportRequest,
    evidence: tuple[EvidenceReference, ...],
) -> tuple[TransportFinding, ...]:
    codes: list[TransportFindingCode] = []
    narrowed = [
        item for item in request.evaluations if item.status is TransportStatus.DOMAIN_NARROWED
    ]
    if narrowed:
        codes.append(TransportFindingCode.SUPPORT_DOMAIN_NARROWED)
        if any(item.dimension.value == "specimen" for item in narrowed):
            codes.append(TransportFindingCode.SPECIMEN_MISMATCH)
    if any(item.metric_value < item.calibration_floor for item in request.evaluations):
        codes.append(TransportFindingCode.CALIBRATION_FLOOR_FAILED)
    if not codes:
        codes.append(TransportFindingCode.PROVISIONAL_ABI_PENDING_REVIEW)
    messages = {
        TransportFindingCode.SUPPORT_DOMAIN_NARROWED: (
            "Support domain was narrowed for one or more transport dimensions."
        ),
        TransportFindingCode.SPECIMEN_MISMATCH: (
            "Specimen transport requires explicit support-domain review."
        ),
        TransportFindingCode.CALIBRATION_FLOOR_FAILED: (
            "A caller-declared calibration floor was not met."
        ),
        TransportFindingCode.PROVISIONAL_ABI_PENDING_REVIEW: (
            "The provisional ABI requires governed owner review."
        ),
    }
    return tuple(
        TransportFinding(
            finding_id=f"finding.m2204.{code.value}",
            code=code,
            message=messages[code],
            evidence=evidence[:1],
        )
        for code in codes
    )


def _report(
    request: EvaluateProteinRnaDiscordanceExternalTransportRequest,
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
    return TransportabilityReport(
        report_id=f"report.m2204.{request_digest.removeprefix('sha256:')}",
        version=request.configuration.version,
        validations=request.validations,
        evaluations=request.evaluations,
        support_domain=SupportDomainUpdate(
            update_id=f"support.m2204.{request_digest.removeprefix('sha256:')}",
            version=request.configuration.version,
            status=TransportStatus.DOMAIN_NARROWED if narrowed else TransportStatus.SUPPORTED,
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
                "No protein-RNA discordance estimate, kinase activity, all-omics fusion, "
                "treatment recommendation, identity inference, or consent inference is emitted."
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


class M2204Engine:
    """Evaluate caller-declared external transport with safe abstention."""

    __slots__ = ()

    def evaluate(self, request: object) -> ProteinRnaDiscordanceExternalTransportResult:
        preflight_m2204_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        return self._result(validated)

    def _result(
        self, request: EvaluateProteinRnaDiscordanceExternalTransportRequest
    ) -> ProteinRnaDiscordanceExternalTransportResult:
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
                TransportFinding(
                    finding_id="finding.m2204.evaluation_incomplete",
                    code=TransportFindingCode.EVALUATION_INCOMPLETE,
                    message=(
                        "One or more configured transport dimensions are not evaluable."
                        if no_evaluable_dimension
                        else "No retained external transport support domain remains."
                    ),
                    evidence=evidence[:1],
                ),
            )
            if abstained
            else _findings(request, evidence)
        )
        payload: dict[str, Any] = {
            "output_type": "protein_rna_discordance_external_transport",
            "result_id": result_identifier(request),
            "result_version": M2204_CONTRACT_VERSION,
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
            "parent_target": "protein-RNA discordance",
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED if abstained else SupportStatus.SUPPORTED,
                reason_code="m2204_transport_abstained"
                if abstained
                else "m2204_transport_evaluated",
                rationale=(
                    "At least one transport dimension is not evaluable; review is required."
                    if abstained
                    else "All retained transport dimensions are independently represented."
                ),
            ),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(request, request_digest),
            "evidence": evidence,
            "limitations": _limitations(abstained=abstained),
            "human_review_required": True,
        }
        provisional = ProteinRnaDiscordanceExternalTransportResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(provisional)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def replay(
        self, result: ProteinRnaDiscordanceExternalTransportResult
    ) -> ProteinRnaDiscordanceExternalTransportResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
            if validated.result_digest != result_payload_digest(validated):
                raise M2204ReplayError  # noqa: TRY301 - digest mismatch is the replay boundary.
            expected = self.evaluate(validated.request)
        except M2204ReplayError:
            raise
        except Exception as error:
            raise M2204ReplayError from error
        if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
            raise M2204ReplayError
        return validated


def evaluate_protein_rna_discordance_external_transport(
    request: object,
) -> ProteinRnaDiscordanceExternalTransportResult:
    """Public stateless M22-04 transport evaluation entry point."""

    return M2204Engine().evaluate(request)


__all__ = [
    "M2204AuthorizationError",
    "M2204Engine",
    "M2204ReplayError",
    "evaluate_protein_rna_discordance_external_transport",
    "preflight_m2204_authorization",
]
