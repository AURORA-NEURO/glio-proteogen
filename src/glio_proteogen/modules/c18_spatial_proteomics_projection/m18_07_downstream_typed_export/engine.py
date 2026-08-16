"""Deterministic, consent-aware M18-07 downstream export engine.

The engine intentionally consumes caller-declared upstream references only.  It
never traverses raw artifacts, authenticates an issuer, infers identity or
consent, or turns unsupported material into a negative finding.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m18_07 import (
    M1807_CONTRACT_VERSION,
    M1807_EVIDENCE_CLAIM,
    M1807_MODULE_ID,
    BiomarkerPanelDownstreamExportResult,
    DownstreamContractObject,
    ExportBiomarkerPanelDownstreamContractRequest,
    ExportFinding,
    ExportFindingCode,
    ExportOwnershipBinding,
    ExportStatus,
    SignedContractEnvelope,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
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

# ruff: noqa: TRY003

_REQUEST_ADAPTER: Final = TypeAdapter(ExportBiomarkerPanelDownstreamContractRequest)
_RESULT_ADAPTER: Final = TypeAdapter(BiomarkerPanelDownstreamExportResult)
_ZERO_DIGEST: Final = "sha256:" + "0" * 64
_EXPECTED_CONTROLS: Final = {
    "approved_configuration": UpstreamDecisionState.ACCEPTED.value,
    "identity_lineage": "resolved",
    "provenance": UpstreamDecisionState.ACCEPTED.value,
    "consent": ConsentState.GRANTED.value,
    "quality": UpstreamDecisionState.ACCEPTED.value,
    "support": UpstreamDecisionState.ACCEPTED.value,
    "intended_use": UpstreamDecisionState.ACCEPTED.value,
}
_ABSTENTION_TERMS: Final = frozenset(
    {
        "unsupported",
        "unknown",
        "missing",
        "not_evaluable",
        "not evaluable",
        "ood",
        "out_of_domain",
        "out of domain",
        "abstain",
        "review_required",
        "review required",
    }
)
_PROHIBITED_TERMS: Final = frozenset(
    {
        "kinase",
        "treatment",
        "therapy",
        "all-omics",
        "all_omics",
        "all omics",
        "identity inference",
        "identity_inference",
        "consent inference",
        "consent_inference",
        "relabel",
        "erase disagreement",
        "negative finding",
    }
)


class M1807AuthorizationError(ValueError):
    """Raised when the seven upstream controls do not authorize export."""


class M1807ExportError(ValueError):
    """Raised when a request cannot be evaluated safely."""


class M1807ReplayError(ValueError):
    """Raised when a result digest or deterministic replay is invalid."""


def _member(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _state(value: object) -> str | None:
    candidate = _member(value, "state")
    return getattr(candidate, "value", candidate) if isinstance(candidate, (str, object)) else None


def preflight_m1807_authorization(candidate: object) -> None:
    """Fail closed before validating or traversing any export fields."""

    references = _member(_member(candidate, "context"), "references")
    if references is None:
        raise M1807AuthorizationError("M18-07 requires all seven upstream controls")
    for role, expected in _EXPECTED_CONTROLS.items():
        decision = _member(references, role)
        actual = _state(decision)
        if actual != expected:
            raise M1807AuthorizationError(
                f"M18-07 control {role} must be {expected}; received {actual}"
            )


def _evidence(
    request: ExportBiomarkerPanelDownstreamContractRequest,
) -> tuple[EvidenceReference, ...]:
    """Build a stable, digest-deduplicated evidence projection."""

    artifacts: list[ArtifactReference] = [request.upstream_result, *request.source_artifacts]
    artifacts.extend(item.reference for item in request.configuration.evidence)
    artifacts.append(request.consent.evidence)
    artifacts.extend(
        item.reference for field in request.fields for item in field.evidence
    )
    refs = request.context.references
    artifacts.extend(
        (
            refs.approved_configuration.evidence,
            refs.identity_lineage.evidence,
            refs.provenance.evidence,
            refs.consent.evidence,
            refs.quality.evidence,
            refs.support.evidence,
            refs.intended_use.evidence,
        )
    )
    unique = {item.digest: item for item in artifacts}
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M1807_EVIDENCE_CLAIM)
        for artifact in unique.values()
    )


def _declared_text(request: ExportBiomarkerPanelDownstreamContractRequest) -> str:
    values = [
        request.request_id,
        request.configuration.configuration_id,
        request.configuration.compatibility.value,
        *(field.field_id for field in request.fields),
        *(field.field_name for field in request.fields),
        *(field.documentation for field in request.fields),
        *(artifact.artifact_id for artifact in request.source_artifacts),
    ]
    return " ".join(values).casefold()


def _uncertainty(*, exported: bool) -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED if exported else EstimateState.NOT_ESTIMABLE,
        probability=0.9 if exported else None,
        rationale=(
            "Caller-declared support, consent and immutable field bindings permit export."
            if exported
            else "The request is outside the safe support or authorization envelope."
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
            "Exportability is sensitive to field documentation, compatibility, support, "
            "consent and upstream control states.",
        ),
    )


def _provenance(
    request: ExportBiomarkerPanelDownstreamContractRequest,
    request_digest: str,
) -> ProvenanceRecord:
    refs = request.context.references
    controls = (
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
    return ProvenanceRecord(
        activity_id=f"activity.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M1807_MODULE_ID,
        module_version=M1807_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(request_digest, request.upstream_result.digest, *(
            artifact.digest for artifact in request.source_artifacts
        )),
        configuration_digest=request.configuration.evidence[0].reference.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=controls,
    )


def _limitations(*, exported: bool) -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="m1807_no_kinase_or_treatment",
            statement=(
                "M18-07 never emits kinase state, generic all-omics fusion or treatment advice."
            ),
        ),
        Limitation(
            code="m1807_caller_declared_authority",
            statement=(
                "Upstream issuer authority and raw artifact contents are not authenticated here."
            ),
        ),
        Limitation(
            code="m1807_exported" if exported else "m1807_abstained",
            statement=(
                "Only documented, versioned fields with immutable ownership are exported."
                if exported
                else "Unsupported, missing, prohibited or unauthorized material is withheld."
            ),
        ),
    )


def _finding(
    finding_id: str,
    code: ExportFindingCode,
    message: str,
    evidence: tuple[EvidenceReference, ...],
) -> ExportFinding:
    return ExportFinding(finding_id=finding_id, code=code, message=message, evidence=evidence[:1])


class M1807Engine:
    """Stateless deterministic downstream typed export evaluator."""

    def validate_request(self, candidate: object) -> ExportBiomarkerPanelDownstreamContractRequest:
        preflight_m1807_authorization(candidate)
        try:
            return _REQUEST_ADAPTER.validate_python(candidate, strict=True)
        except Exception as error:
            raise M1807ExportError("M18-07 request is invalid") from error

    def export(self, candidate: object) -> BiomarkerPanelDownstreamExportResult:
        request = self.validate_request(candidate)
        request_digest = canonical_request_digest(request)
        evidence = _evidence(request)
        declared = _declared_text(request)
        prohibited = sorted(term for term in _PROHIBITED_TERMS if term in declared)
        unsupported = sorted(term for term in _ABSTENTION_TERMS if term in declared)
        missing_documentation = [
            field.field_id for field in request.fields if not field.documentation
        ]
        supported = (
            not prohibited
            and not unsupported
            and not missing_documentation
            and request.consent.state is ConsentState.GRANTED
            and request.support_decision.status is SupportStatus.SUPPORTED
            and request.configuration.documented_fields_only
        )
        findings: list[ExportFinding] = []
        if prohibited:
            findings.append(_finding(
                "finding.prohibited-boundary", ExportFindingCode.COMPATIBILITY_MISMATCH,
                "A prohibited responsibility is outside the M18-07 export boundary.", evidence,
            ))
        if unsupported:
            findings.append(
                _finding(
                    "finding.unsupported",
                    ExportFindingCode.UPSTREAM_UNSUPPORTED,
                    "Unsupported or unresolved material cannot be exported as a negative finding.",
                    evidence,
                )
            )
        if missing_documentation:
            findings.append(_finding(
                "finding.undocumented", ExportFindingCode.FIELD_UNDOCUMENTED,
                "Every exported field must have caller-declared documentation.", evidence,
            ))
        if request.consent.state is not ConsentState.GRANTED:
            findings.append(_finding(
                "finding.consent", ExportFindingCode.CONSENT_WITHHELD,
                "Consent is not granted; no downstream contract may be emitted.", evidence,
            ))
        if request.support_decision.status is not SupportStatus.SUPPORTED:
            findings.append(_finding(
                "finding.support", ExportFindingCode.SUPPORT_BOUNDARY,
                "The caller-declared upstream support status is not supported.", evidence,
            ))
        if not findings:
            findings.append(_finding(
                "finding.provisional-abi", ExportFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                "The M18-07 ABI remains provisional pending owner confirmation.", evidence,
            ))
        ownership = ExportOwnershipBinding(
            owning_module=M1807_MODULE_ID,
            owner="Platform engineering",
            ownership_statement="M18-07 exclusively owns this signed downstream typed export.",
            evidence=evidence[:1],
        )
        signature = SignedContractEnvelope(
            signer_id=request.context.actor_id,
            algorithm="caller-declared-sha256",
            signed_payload_digest=sha256_digest({
                "request_digest": request_digest,
                "fields": request.fields,
                "configuration": request.configuration,
            }),
            signature_digest=sha256_digest(
                {"request_digest": request_digest, "owner": M1807_MODULE_ID}
            ),
            evidence=evidence[:1],
        )
        contract: DownstreamContractObject | None = None
        if supported:
            contract = DownstreamContractObject(
                contract_id=f"contract.{request_digest.removeprefix('sha256:')}",
                version=request.configuration.version,
                fields=request.fields,
                ownership=ownership,
                consent=request.consent,
                support_decision=request.support_decision,
                configuration=request.configuration,
                signature=signature,
                uncertainty=_uncertainty(exported=True),
                provenance=_provenance(request, request_digest),
                evidence=evidence,
            )
        status = ExportStatus.EXPORTED if contract is not None else ExportStatus.ABSTAINED
        support = (
            SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="m1807_exported",
                rationale="All documented fields and required controls are supported.",
            )
            if supported
            else SupportDecision(
                status=(
                    SupportStatus.UNSUPPORTED
                    if (
                        prohibited
                        or unsupported
                        or request.support_decision.status is SupportStatus.UNSUPPORTED
                    )
                    else SupportStatus.REVIEW_REQUIRED
                ),
                reason_code="m1807_abstained",
                rationale=(
                    "Safe abstention preserves ownership, disagreement and support semantics."
                ),
            )
        )
        payload: dict[str, Any] = {
            "output_type": "biomarker_panel_downstream_contract",
            "result_id": f"result.{request_digest.removeprefix('sha256:')}",
            "result_version": M1807_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": status,
            "contract": contract,
            "findings": tuple(findings),
            "abstention_reason": (
                None if supported else "M18-07 export is outside the safe support envelope."
            ),
            "parent_target": "biomarker panel",
            "emits_parent": False,
            "support_decision": support,
            "uncertainty": _uncertainty(exported=supported),
            "provenance": _provenance(request, request_digest),
            "evidence": evidence,
            "limitations": _limitations(exported=supported),
            "human_review_required": not supported or bool(findings),
        }
        constructed = BiomarkerPanelDownstreamExportResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(constructed)
        try:
            return _RESULT_ADAPTER.validate_python(payload, strict=True)
        except Exception as error:
            raise M1807ExportError("M18-07 result construction failed safely") from error

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> BiomarkerPanelDownstreamExportResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1807ReplayError("M18-07 result is invalid") from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1807ReplayError("M18-07 result digest mismatch")
        if replay:
            expected = self.export(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1807ReplayError("M18-07 deterministic replay mismatch")
        return validated


def export_biomarker_panel_downstream_contract(
    candidate: object,
) -> BiomarkerPanelDownstreamExportResult:
    """Public M18-07 export operation."""

    return M1807Engine().export(candidate)


__all__ = [
    "M1807AuthorizationError",
    "M1807Engine",
    "M1807ExportError",
    "M1807ReplayError",
    "export_biomarker_panel_downstream_contract",
    "preflight_m1807_authorization",
]
