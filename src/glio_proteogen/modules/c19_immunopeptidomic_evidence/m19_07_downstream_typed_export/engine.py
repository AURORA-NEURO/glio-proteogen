"""Deterministic, support-aware M19-07 downstream export engine.

The engine consumes only typed caller-declared references.  It never traverses
raw evidence, authenticates an issuer, infers identity or consent, relabels a
different module's output, or turns unsupported material into a negative
finding.  Every result can be verified by canonical digest and deterministic
replay.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m19_07 import (
    M1907_CONTRACT_VERSION,
    M1907_EVIDENCE_CLAIM,
    M1907_MODULE_ID,
    M1907_PROHIBITED_CLAIM_TERMS,
    DownstreamContractObject,
    ExportFinding,
    ExportFindingCode,
    ExportOwnershipBinding,
    ExportProteotypeDownstreamContractRequest,
    ExportStatus,
    ProteotypeDownstreamExportResult,
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

_REQUEST_ADAPTER: Final = TypeAdapter(ExportProteotypeDownstreamContractRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteotypeDownstreamExportResult)
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
_PROHIBITED_TERMS: Final = frozenset(M1907_PROHIBITED_CLAIM_TERMS) | frozenset(
    {
        "kinase",
        "treatment",
        "therapy",
        "all_omics",
        "all omics",
        "identity_inference",
        "consent_inference",
        "relabel",
        "erase disagreement",
        "negative finding",
    }
)


class M1907AuthorizationError(ValueError):
    """Raised when the seven upstream controls do not authorize export."""


class M1907ExportError(ValueError):
    """Raised when a request cannot be evaluated safely."""


class M1907ReplayError(ValueError):
    """Raised when a result digest or deterministic replay is invalid."""


def _member(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _state(value: object) -> str | None:
    candidate = _member(value, "state")
    if isinstance(candidate, str):
        return candidate
    state_value = getattr(candidate, "value", None)
    return state_value if isinstance(state_value, str) else None


def preflight_m1907_authorization(candidate: object) -> None:
    """Fail closed before parsing or inspecting export fields."""

    references = _member(_member(candidate, "context"), "references")
    if references is None:
        raise M1907AuthorizationError("M19-07 requires all seven upstream controls")
    for role, expected in _EXPECTED_CONTROLS.items():
        decision = _member(references, role)
        actual = _state(decision)
        if actual != expected:
            raise M1907AuthorizationError(
                f"M19-07 control {role} must be {expected}; received {actual}"
            )


def _evidence(request: ExportProteotypeDownstreamContractRequest) -> tuple[EvidenceReference, ...]:
    """Build a stable, digest-deduplicated evidence projection."""

    artifacts: list[ArtifactReference] = [request.upstream_result, *request.source_artifacts]
    artifacts.extend(item.reference for item in request.configuration.evidence)
    artifacts.append(request.consent.evidence)
    artifacts.extend(item.reference for field in request.fields for item in field.evidence)
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
        EvidenceReference(reference=artifact, role="evidence", claim=M1907_EVIDENCE_CLAIM)
        for artifact in unique.values()
    )


def _declared_text(request: ExportProteotypeDownstreamContractRequest) -> str:
    values = [
        request.request_id,
        request.configuration.configuration_id,
        request.configuration.compatibility.value,
        *(field.field_id for field in request.fields),
        *(field.field_name for field in request.fields),
        *(field.documentation for field in request.fields),
        *(artifact.artifact_id for artifact in request.source_artifacts),
        *_claim_texts(request),
    ]
    return " ".join(values).casefold()


def _claim_texts(request: ExportProteotypeDownstreamContractRequest) -> tuple[str, ...]:
    """Collect caller-controlled prose before any export contract is emitted."""

    texts: list[str] = [request.support_decision.rationale]
    texts.extend(field.documentation for field in request.fields)
    texts.extend(evidence.claim for evidence in request.configuration.evidence)
    texts.extend(evidence.claim for field in request.fields for evidence in field.evidence)
    return tuple(texts)


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
    request: ExportProteotypeDownstreamContractRequest,
    request_digest: str,
) -> ProvenanceRecord:
    refs = request.context.references
    input_digests = tuple(
        dict.fromkeys(
            (
                request_digest,
                request.upstream_result.digest,
                *(artifact.digest for artifact in request.source_artifacts),
                *(item.reference.digest for item in request.configuration.evidence),
                request.consent.evidence.digest,
                *(item.reference.digest for field in request.fields for item in field.evidence),
                refs.approved_configuration.evidence.digest,
                refs.identity_lineage.evidence.digest,
                refs.provenance.evidence.digest,
                refs.consent.evidence.digest,
                refs.quality.evidence.digest,
                refs.support.evidence.digest,
                refs.intended_use.evidence.digest,
            )
        )
    )
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
        module_id=M1907_MODULE_ID,
        module_version=M1907_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
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
            code="m1907_no_kinase_or_treatment",
            statement=(
                "M19-07 never emits kinase state, generic all-omics fusion or treatment advice."
            ),
        ),
        Limitation(
            code="m1907_caller_declared_authority",
            statement=(
                "Upstream issuer authority and raw artifact contents are not authenticated here."
            ),
        ),
        Limitation(
            code="m1907_exported" if exported else "m1907_abstained",
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


class M1907Engine:
    """Stateless deterministic downstream typed export evaluator."""

    def validate_request(self, candidate: object) -> ExportProteotypeDownstreamContractRequest:
        preflight_m1907_authorization(candidate)
        try:
            return _REQUEST_ADAPTER.validate_python(candidate, strict=True)
        except Exception as error:
            raise M1907ExportError("M19-07 request is invalid") from error

    def export(self, candidate: object) -> ProteotypeDownstreamExportResult:
        request = self.validate_request(candidate)
        request_digest = canonical_request_digest(request)
        evidence = _evidence(request)
        declared = _declared_text(request)
        prohibited = sorted(term for term in _PROHIBITED_TERMS if term in declared)
        unsupported = sorted(term for term in _ABSTENTION_TERMS if term in declared)
        ownership_mismatch = any(
            field.owner != "Scientific engineering" for field in request.fields
        )
        supported = (
            not prohibited
            and not unsupported
            and not ownership_mismatch
            and request.consent.state is ConsentState.GRANTED
            and request.support_decision.status is SupportStatus.SUPPORTED
            and request.configuration.documented_fields_only
        )
        findings: list[ExportFinding] = []
        if prohibited:
            findings.append(
                _finding(
                    "finding.prohibited-boundary",
                    ExportFindingCode.PROHIBITED_CLAIM_BOUNDARY,
                    (
                        "Caller-controlled export text exceeds the M19-07 claims ceiling; "
                        "no downstream contract is emitted."
                    ),
                    evidence,
                )
            )
        if unsupported:
            findings.append(
                _finding(
                    "finding.unsupported",
                    ExportFindingCode.UPSTREAM_UNSUPPORTED,
                    "Unsupported or unresolved material cannot be exported as a negative finding.",
                    evidence,
                )
            )
        if request.support_decision.status is not SupportStatus.SUPPORTED:
            findings.append(
                _finding(
                    "finding.support",
                    ExportFindingCode.SUPPORT_BOUNDARY,
                    "The caller-declared upstream support status is not supported.",
                    evidence,
                )
            )
        if ownership_mismatch:
            findings.append(
                _finding(
                    "finding.ownership",
                    ExportFindingCode.COMPATIBILITY_MISMATCH,
                    "Every exported field must preserve the M19-07 ownership binding.",
                    evidence,
                )
            )
        if not findings:
            findings.append(
                _finding(
                    "finding.provisional-abi",
                    ExportFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                    "The M19-07 ABI remains provisional pending owner confirmation.",
                    evidence,
                )
            )
        ownership = ExportOwnershipBinding(
            owning_module=M1907_MODULE_ID,
            owner="Scientific engineering",
            ownership_statement="M19-07 exclusively owns this signed downstream typed export.",
            evidence=evidence[:1],
        )
        signature = SignedContractEnvelope(
            signer_id=request.context.actor_id,
            algorithm="caller-declared-sha256",
            signed_payload_digest=sha256_digest(
                {
                    "request_digest": request_digest,
                    "fields": request.fields,
                    "configuration": request.configuration,
                }
            ),
            signature_digest=sha256_digest(
                {"request_digest": request_digest, "owner": M1907_MODULE_ID}
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
                reason_code="m1907_exported",
                rationale="All documented fields and required controls are supported.",
            )
            if supported
            else SupportDecision(
                status=(
                    SupportStatus.UNSUPPORTED
                    if prohibited
                    or unsupported
                    or request.support_decision.status is SupportStatus.UNSUPPORTED
                    else SupportStatus.REVIEW_REQUIRED
                ),
                reason_code="m1907_abstained",
                rationale=(
                    "Safe abstention preserves ownership, disagreement and support semantics."
                ),
            )
        )
        payload: dict[str, Any] = {
            "output_type": "proteotype_downstream_contract",
            "result_id": f"result.{request_digest.removeprefix('sha256:')}",
            "result_version": M1907_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": status,
            "contract": contract,
            "findings": tuple(findings),
            "abstention_reason": (
                None if supported else "M19-07 export is outside the safe support envelope."
            ),
            "parent_target": "proteotype",
            "emits_parent": False,
            "support_decision": support,
            "uncertainty": _uncertainty(exported=supported),
            "provenance": _provenance(request, request_digest),
            "evidence": evidence,
            "limitations": _limitations(exported=supported),
            "human_review_required": not supported or bool(findings),
        }
        constructed = ProteotypeDownstreamExportResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(constructed)
        try:
            return _RESULT_ADAPTER.validate_python(payload, strict=True)
        except Exception as error:
            raise M1907ExportError("M19-07 result construction failed safely") from error

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteotypeDownstreamExportResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1907ReplayError("M19-07 result is invalid") from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1907ReplayError("M19-07 result digest mismatch")
        if replay:
            expected = self.export(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1907ReplayError("M19-07 deterministic replay mismatch")
        return validated


def export_proteotype_downstream_contract(candidate: object) -> ProteotypeDownstreamExportResult:
    """Public M19-07 export operation."""

    return M1907Engine().export(candidate)
